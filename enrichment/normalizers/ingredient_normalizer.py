"""Phase 1: multi-tier ingredient normalization pipeline.

Tier order:
  1. PubChem  — chemical identity authority (CAS, IUPAC)
  2. DSLD     — supplement-specific naming (UNII codes, label variants)
  3. RapidFuzz — match against already-resolved Ingredient_Canonical rows
  4. Flag     — low-confidence result returned with manual_review flag
"""
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
CONFIDENCE_THRESHOLD = 0.85

logger = logging.getLogger("agnes.normalizer")


class IngredientNormalizer:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        from enrichment.parsers.sku_parser import parse_all_raw_material_skus
        from enrichment.sources.pubchem import PubChemClient
        from enrichment.sources.dsld import DSLDClient
        from enrichment.normalizers.fuzzy_matcher import FuzzyMatcher

        skus = parse_all_raw_material_skus(self.db_path)
        logger.info(f"Normalizing {len(skus)} raw-material SKUs")

        # Instantiate clients once — avoids reopening SQLite on every iteration
        self._pubchem = PubChemClient(self.db_path)
        self._dsld = DSLDClient(self.db_path)
        self._fuzzy = FuzzyMatcher(self.db_path)

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        # Deduplicate: resolve each unique ingredient name once, then fan out to all SKUs
        name_to_result: dict[str, dict | None] = {}
        pending: list = []  # skus that need normalization

        for parsed in skus:
            if parsed.is_complex:
                logger.debug(f"Skipping complex ingredient: {parsed.extracted_name}")
                self._log(conn, parsed.product_id, "sku_parse", "skipped", 0.0,
                          "complex", "proprietary blend / complex — skipped")
                continue

            existing = conn.execute(
                "SELECT Confidence FROM SKU_To_Canonical WHERE ProductId = ?",
                (parsed.product_id,),
            ).fetchone()
            if existing and existing[0] >= CONFIDENCE_THRESHOLD:
                self._log(conn, parsed.product_id, "sku_parse", "skipped", existing[0],
                          "existing", "already mapped above threshold")
                continue

            pending.append(parsed)

        # Resolve each unique name once, concurrently
        unique_names = list(dict.fromkeys(p.extracted_name for p in pending))
        logger.info(f"{len(pending)} SKUs → {len(unique_names)} unique names to resolve")
        total = len(unique_names)

        def _resolve(args: tuple[int, str]) -> tuple[str, dict | None]:
            i, name = args
            logger.info(f"[{i}/{total}] Resolving '{name}'")
            return name, self._normalize(name)

        # 8 workers: enough to saturate PubChem's 5 req/sec limit across threads
        # while staying safely under the 400 req/min cap
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_resolve, (i, n)): n
                       for i, n in enumerate(unique_names, 1)}
            for future in as_completed(futures):
                name, result = future.result()
                name_to_result[name] = result

        # Write mappings for all pending SKUs
        for parsed in pending:
            result = name_to_result.get(parsed.extracted_name)
            if result:
                self._upsert_mapping(conn, parsed.product_id, parsed.extracted_name, result)

        conn.commit()
        conn.close()
        logger.info("Phase 1 normalization complete.")

    def _normalize(self, name: str) -> dict | None:
        pubchem = self._pubchem
        dsld = self._dsld
        fuzzy = self._fuzzy

        # Tier 1: PubChem
        result = pubchem.lookup(name)
        if result and result["confidence"] >= CONFIDENCE_THRESHOLD:
            logger.debug(f"PubChem hit for '{name}' (conf={result['confidence']:.2f})")
            return result

        # Tier 2: DSLD
        result2 = dsld.search_ingredient(name)
        if result2 and result2["confidence"] >= CONFIDENCE_THRESHOLD:
            logger.debug(f"DSLD hit for '{name}' (conf={result2['confidence']:.2f})")
            return result2

        # Tier 3: Fuzzy match against existing canonicals
        result3 = fuzzy.match(name)
        if result3 and result3["confidence"] >= CONFIDENCE_THRESHOLD:
            logger.debug(f"Fuzzy hit for '{name}' (conf={result3['confidence']:.2f})")
            return result3

        # Tier 4: Best-effort + flag
        best = result3 or result2 or result
        if best:
            best["flag"] = "manual_review"
            logger.debug(f"Low-confidence match for '{name}' (conf={best['confidence']:.2f}) — flagged")
            return best

        logger.warning(f"No match found for '{name}'")
        return None

    def _upsert_mapping(self, conn: sqlite3.Connection, product_id: int,
                        extracted_name: str, result: dict) -> None:
        canonical_id = self._get_or_create_canonical(conn, result)
        conn.execute(
            """INSERT OR REPLACE INTO SKU_To_Canonical
               (ProductId, CanonicalId, ExtractedName, MatchMethod, Confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (product_id, canonical_id, extracted_name,
             result.get("method", "unknown"), result.get("confidence", 0.0)),
        )
        status = "success" if not result.get("flag") else "fallback"
        self._log(conn, product_id, result.get("method", "unknown"), status,
                  result.get("confidence", 0.0), result.get("method"))

    def _get_or_create_canonical(self, conn: sqlite3.Connection, result: dict) -> int:
        """Return existing canonical Id or insert a new row."""
        cas = result.get("cas_number")
        name = result.get("name", "")

        if cas:
            row = conn.execute(
                "SELECT Id FROM Ingredient_Canonical WHERE CAS_Number = ?", (cas,)
            ).fetchone()
            if row:
                return row[0]

        row = conn.execute(
            "SELECT Id FROM Ingredient_Canonical WHERE Name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            return row[0]

        cursor = conn.execute(
            """INSERT INTO Ingredient_Canonical
               (Name, CAS_Number, PubChem_CID, IUPAC_Name, Molecular_Formula,
                Function, Confidence, Sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                cas,
                result.get("pubchem_cid"),
                result.get("iupac_name"),
                result.get("molecular_formula"),
                result.get("function"),
                result.get("confidence", 0.0),
                json.dumps(result.get("sources", [])),
            ),
        )
        return cursor.lastrowid

    def _log(self, conn: sqlite3.Connection, product_id: int, step: str,
             status: str, confidence: float, method: str | None,
             error_msg: str | None = None) -> None:
        try:
            conn.execute(
                """INSERT INTO Enrichment_Run_Log
                   (ProductId, Phase, Step, Status, Confidence, Method, Error_Msg)
                   VALUES (?, 1, ?, ?, ?, ?, ?)""",
                (product_id, step, status, confidence, method, error_msg),
            )
        except Exception:
            pass
