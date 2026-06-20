"""Phase 1 backfill: populate SMILES, UNII_Code, MatchScore on existing canonical rows."""
import logging
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.backfill_phase1")


def backfill_smiles(db_path=ENRICHED_DB) -> None:
    """Fetch IsomericSMILES from PubChem for all canonicals that have a PubChem_CID."""
    from enrichment.sources.pubchem import PubChemClient
    client = PubChemClient(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT Id, PubChem_CID FROM Ingredient_Canonical "
        "WHERE PubChem_CID IS NOT NULL AND SMILES IS NULL"
    ).fetchall()
    logger.info(f"SMILES backfill: {len(rows)} canonicals to process")
    for canonical_id, cid in rows:
        # Commit before API call so the write lock is released, allowing PubChem
        # client's cache writes (_set_cache opens its own connection) to succeed.
        conn.commit()
        smiles = client.get_isomeric_smiles(cid)
        conn.execute("UPDATE Ingredient_Canonical SET SMILES = ? WHERE Id = ?", (smiles, canonical_id))
        conn.commit()
        status = "success" if smiles else "no_match"
        conn.execute(
            "INSERT INTO Enrichment_Run_Log "
            "(ProductId, Phase, Step, Status, Confidence, Method) VALUES (NULL, 1, 'smiles_backfill', ?, 0.97, 'pubchem')",
            (status,)
        )
    conn.commit()
    conn.close()
    logger.info(f"SMILES backfill complete: {len(rows)} rows processed")


def backfill_unii(db_path=ENRICHED_DB) -> None:
    """Backfill UNII_Code for canonicals by searching DSLD and reading ingredientRows."""
    from enrichment.sources.dsld import DSLDClient
    from rapidfuzz import fuzz, process as fuzz_process
    client = DSLDClient(db_path)
    # Fetch rows with a short-lived read connection so no open transaction
    # blocks DSLD cache writes during the API loop.
    with sqlite3.connect(db_path, timeout=30) as _r:
        rows = _r.execute(
            "SELECT Id, Name FROM Ingredient_Canonical WHERE UNII_Code IS NULL"
        ).fetchall()
    logger.info(f"UNII backfill: {len(rows)} canonicals to process")
    updated = 0
    for canonical_id, name in rows:
        # search_ingredient() doesn't return uniiCode — must fetch label ingredientRows
        data = client._search({"q": name, "size": 3})
        if not data or not data.get("hits"):
            time.sleep(0.25)
            continue

        unii = None
        for hit in data["hits"]:
            label_id = hit.get("_id")
            if not label_id:
                continue
            ingredients = client.extract_label_ingredients(label_id)
            if not ingredients:
                continue
            ing_names = [i["ingredient_name"] for i in ingredients]
            best = fuzz_process.extractOne(name, ing_names, scorer=fuzz.token_set_ratio)
            if best and best[1] >= 80:
                idx = ing_names.index(best[0])
                unii = ingredients[idx].get("unii_code")
                if unii:
                    break

        if unii:
            # Open a fresh connection per write so DSLD cache writes never contend.
            with sqlite3.connect(db_path, timeout=30) as _w:
                _w.execute(
                    "UPDATE Ingredient_Canonical SET UNII_Code = ? WHERE Id = ?",
                    (unii, canonical_id)
                )
            updated += 1

        time.sleep(0.25)

    logger.info(f"UNII backfill: {updated}/{len(rows)} rows populated")


def backfill_unii_from_pubchem_synonyms(db_path=ENRICHED_DB) -> None:
    """Extract UNII codes from PubChem synonym lists for canonicals with a PubChem_CID."""
    from enrichment.sources.pubchem import PubChemClient
    client = PubChemClient(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        rows = conn.execute(
            "SELECT Id, Name, PubChem_CID FROM Ingredient_Canonical "
            "WHERE PubChem_CID IS NOT NULL AND UNII_Code IS NULL"
        ).fetchall()
    logger.info(f"PubChem UNII backfill: {len(rows)} canonicals to process")
    updated = 0
    for canonical_id, name, cid in rows:
        unii = client.get_unii_from_synonyms(cid)
        if unii:
            with sqlite3.connect(db_path, timeout=30) as w:
                w.execute(
                    "UPDATE Ingredient_Canonical SET UNII_Code = ? WHERE Id = ?",
                    (unii, canonical_id)
                )
            logger.info(f"  UNII set: {name} (CID={cid}) → {unii}")
            updated += 1
    logger.info(f"PubChem UNII backfill: {updated}/{len(rows)} rows populated")


def backfill_cid_gaps(db_path=ENRICHED_DB) -> None:
    """Populate PubChem_CID for canonicals that currently have none.

    Tries identifiers in priority order: UNII → CAS → canonical name.
    Run backfill_smiles() afterwards to pick up the newly found CIDs.
    """
    from enrichment.sources.pubchem import PubChemClient, _extract_cas
    client = PubChemClient(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT Id, Name, UNII_Code, CAS_Number FROM Ingredient_Canonical WHERE PubChem_CID IS NULL"
    ).fetchall()
    logger.info(f"CID gap backfill: {len(rows)} canonicals to process")
    updated = 0
    for canonical_id, name, unii, cas in rows:
        cid = None

        if unii and unii != "0":
            conn.commit()
            cid = client.get_cid_by_name(unii)

        if not cid and cas:
            conn.commit()
            cid = client.get_cid_by_name(cas)

        if not cid:
            conn.commit()
            cid = client.get_cid_by_name(name)

        if cid:
            conn.execute(
                "UPDATE Ingredient_Canonical SET PubChem_CID = ? WHERE Id = ?",
                (cid, canonical_id),
            )
            if not cas:
                try:
                    synonyms = client._get_synonyms(cid)
                    cas_found = _extract_cas(synonyms)
                    if cas_found:
                        conn.execute(
                            "UPDATE Ingredient_Canonical SET CAS_Number = ? WHERE Id = ? AND CAS_Number IS NULL",
                            (cas_found, canonical_id),
                        )
                except Exception:
                    pass
            conn.commit()
            logger.info(f"  CID found: {name!r} → CID={cid}")
            updated += 1
        time.sleep(0.05)

    conn.close()
    logger.info(f"CID gap backfill complete: {updated}/{len(rows)} new CIDs")


def backfill_match_scores(db_path=ENRICHED_DB) -> None:
    """Re-compute MatchScore for fuzzy-matched SKU_To_Canonical rows (no API calls)."""
    from rapidfuzz import fuzz
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT stc.ProductId, stc.ExtractedName, ic.Name
        FROM SKU_To_Canonical stc
        JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
        WHERE stc.MatchScore IS NULL AND stc.MatchMethod = 'fuzzy'
    """).fetchall()
    logger.info(f"MatchScore backfill: {len(rows)} fuzzy rows to score")
    for product_id, extracted, canonical_name in rows:
        score = fuzz.token_set_ratio(extracted, canonical_name) if extracted else None
        conn.execute(
            "UPDATE SKU_To_Canonical SET MatchScore = ? WHERE ProductId = ?",
            (score, product_id)
        )
    conn.commit()
    conn.close()
    logger.info("MatchScore backfill complete")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    )
    backfill_cid_gaps()   # must run before backfill_smiles so new CIDs are present
    backfill_smiles()
    backfill_unii_from_pubchem_synonyms()  # picks up UNIIs for newly-CID'd rows
    backfill_unii()
    backfill_match_scores()
