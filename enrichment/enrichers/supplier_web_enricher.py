"""Async enricher: discovers bulk ingredient suppliers via Google Search → Supplier_Commercial."""
import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.supplier_web_enricher")

_CONFIDENCE_WEB = 0.65


def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    """Mirror of research_agent._parse_suppliers — extract JSON array from model output."""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    if raw.strip():
        return [{"supplier_name": "research_result", "notes": raw[:400]}]
    return []


def _parse_price(price_str: str | None) -> float | None:
    """Extract a float from strings like '$12-18', '~15', '12.50 USD/kg'."""
    if not price_str:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(price_str))
    if not nums:
        return None
    values = [float(n) for n in nums[:2]]
    return round(sum(values) / len(values), 4)


def _parse_moq(moq_str: str | None) -> float | None:
    """Extract float from '25 kg', '1-5 kg', '100kg'."""
    if not moq_str:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", str(moq_str))
    return float(nums[0]) if nums else None


class SupplierWebEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def _get_targets(self) -> list[tuple[int, str, str | None]]:
        """Return (canonical_id, name, grade_flag) for canonicals with no web-search commercial rows."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT ic.Id, ic.Name, ic.Grade_Flag
               FROM Ingredient_Canonical ic
               WHERE ic.UNII_Code IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM Supplier_Commercial sc
                   WHERE sc.CanonicalIngredientId = ic.Id
                     AND sc.Price_Source = 'google_search'
               )
               ORDER BY ic.Name"""
        ).fetchall()
        conn.close()
        return [(r[0], r[1], r[2]) for r in rows]

    def _upsert_supplier(self, conn: sqlite3.Connection, supplier_name: str, country: str | None) -> int:
        existing = conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()
        if existing:
            return existing[0]
        cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name, Country) VALUES (?, ?)", (supplier_name, country))
        sid = cur.lastrowid or conn.execute("SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)).fetchone()[0]
        return sid

    def _write_commercial(
        self, conn: sqlite3.Connection,
        supplier_id: int, canonical_id: int,
        parsed: dict, source_url: str | None
    ) -> None:
        price = _parse_price(parsed.get("price_range_usd_per_kg"))
        moq = _parse_moq(parsed.get("moq_range_kg"))
        country = (parsed.get("country") or "")[:10] or None
        purity_q = (parsed.get("certifications") or [])
        purity_qualifier = ", ".join(purity_q[:3]) if purity_q else None

        conn.execute(
            """INSERT OR REPLACE INTO Supplier_Commercial
               (SupplierId, CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG,
                Country_Origin, Price_Type, Price_Source, Confidence,
                Source_URL, Last_Updated, Grade_Unverified, Purity_Qualifier)
               VALUES (?, ?, ?, ?, ?, 'web_search', 'google_search', ?, ?, datetime('now'), 1, ?)""",
            (supplier_id, canonical_id, price, moq, country, _CONFIDENCE_WEB, source_url, purity_qualifier)
        )

    async def enrich_ingredient(self, canonical_id: int, ingredient_name: str) -> int:
        """Discover and persist suppliers for one ingredient. Returns count inserted."""
        from orchestration.agents.search_sub_agent import search
        try:
            raw = await search(ingredient_name, query_hint="bulk supplier B2B price MOQ certificate")
        except Exception as e:
            logger.warning(f"Search failed for {ingredient_name}: {e}")
            return 0

        suppliers = _parse_suppliers(raw, ingredient_name)
        written = 0
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for s in suppliers:
            name = (s.get("supplier_name") or "").strip()[:200]
            if not name or name == "research_result":
                continue
            try:
                supplier_id = self._upsert_supplier(conn, name, s.get("country"))
                self._write_commercial(conn, supplier_id, canonical_id, s, s.get("website"))
                written += 1
            except Exception as e:
                logger.warning(f"  Failed to write supplier {name!r}: {e}")
        conn.execute(
            """INSERT INTO Enrichment_Run_Log (ProductId, Phase, Step, Status, Confidence, Method)
               VALUES (NULL, 3, 'supplier_web_enrich', 'success', 0.65, 'google_search')"""
        )
        conn.commit()
        conn.close()
        logger.info(f"  {ingredient_name}: {len(suppliers)} found → {written} written to Supplier_Commercial")
        return written

    async def run_batch(self, limit: int | None = None) -> dict:
        targets = self._get_targets()
        if limit:
            targets = targets[:limit]
        logger.info(f"SupplierWebEnricher: {len(targets)} ingredients to enrich")
        total = 0
        for canonical_id, name, grade in targets:
            n = await self.enrich_ingredient(canonical_id, name)
            total += n
        return {"processed": len(targets), "total_suppliers_written": total}
