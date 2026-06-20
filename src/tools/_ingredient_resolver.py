"""
Shared 3-stage ingredient name resolver: exact → synonym → fuzzy.
Returns a structured resolution dict; never raises.
"""
import sqlite3
from pathlib import Path

from rapidfuzz import fuzz

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "db_enriched.sqlite"

_SYNONYMS: dict[str, str] = {
    "vitamin c": "Vitamin C",
    "ascorbic acid": "Vitamin C",
    "l-ascorbic acid": "Vitamin C",
    "vitamin d": "Vitamin D",
    "vitamin d3": "Vitamin D",
    "cholecalciferol": "Vitamin D",
    "vitamin d2": "Vitamin D",
    "ergocalciferol": "Vitamin D",
    "vitamin e": "Vitamin E",
    "alpha-tocopherol": "Vitamin E",
    "tocopherol": "Vitamin E",
    "vitamin b1": "Thiamine",
    "thiamine": "Thiamine",
    "thiamin": "Thiamine",
    "vitamin b2": "Riboflavin",
    "riboflavin": "Riboflavin",
    "vitamin b3": "Niacinamide",
    "niacin": "Niacinamide",
    "nicotinamide": "Niacinamide",
    "niacinamide": "Niacinamide",
    "vitamin b5": "Pantothenic Acid",
    "pantothenic acid": "Pantothenic Acid",
    "calcium pantothenate": "Pantothenic Acid",
    "vitamin b6": "Pyridoxine HCl",
    "pyridoxine": "Pyridoxine HCl",
    "pyridoxine hcl": "Pyridoxine HCl",
    "vitamin b7": "Biotin",
    "biotin": "Biotin",
    "vitamin b9": "Folate",
    "folate": "Folate",
    "folic acid": "Folate",
    "vitamin b12": "Vitamin B12",
    "cyanocobalamin": "Vitamin B12",
    "methylcobalamin": "Vitamin B12",
    "cobalamin": "Vitamin B12",
    "vitamin k": "Vitamin K",
    "vitamin k2": "Vitamin K",
    "menaquinone": "Vitamin K",
    "vitamin k1": "Vitamin K",
    "phytonadione": "Vitamin K",
    "phylloquinone": "Vitamin K",
    "vitamin a": "Vitamin A",
    "retinol": "Vitamin A",
    "beta-carotene": "Vitamin A",
    "beta carotene": "Vitamin A",
    "zinc": "Zinc",
    "zinc oxide": "Zinc",
    "zinc gluconate": "Zinc",
    "zinc sulfate": "Zinc",
    "zinc glycinate": "Zinc",
    "zinc picolinate": "Zinc",
    "magnesium": "Magnesium",
    "magnesium oxide": "Magnesium",
    "magnesium citrate": "Magnesium",
    "magnesium glycinate": "Magnesium",
    "magnesium malate": "Magnesium",
    "magnesium stearate": "Magnesium Stearate",
    "mg stearate": "Magnesium Stearate",
    "iron": "Iron",
    "ferrous sulfate": "Iron",
    "ferrous gluconate": "Iron",
    "ferrous fumarate": "Iron",
    "calcium": "Calcium",
    "calcium carbonate": "Calcium",
    "calcium citrate": "Calcium",
    "calcium phosphate": "Calcium",
    "calcium stearate": "Calcium Stearate",
    "mcc": "Cellulose",
    "microcrystalline cellulose": "Cellulose",
    "cellulose": "Cellulose",
    "hpmc": "Hydroxypropyl Methylcellulose",
    "hydroxypropyl methylcellulose": "Hydroxypropyl Methylcellulose",
    "hypromellose": "Hydroxypropyl Methylcellulose",
    "silicon dioxide": "Silicon Dioxide",
    "silica": "Silicon Dioxide",
    "fumed silica": "Silicon Dioxide",
    "titanium dioxide": "Titanium Dioxide",
    "stearic acid": "Stearic Acid",
    "d3": "Vitamin D",
    "d-3": "Vitamin D",
    "k2": "Vitamin K",
    "omega-3": "Fish Oil",
    "omega 3": "Fish Oil",
    "fish oil": "Fish Oil",
    "dha": "Fish Oil",
    "epa": "Fish Oil",
    "cod liver oil": "Fish Oil",
    "coq10": "Coenzyme Q10",
    "co q10": "Coenzyme Q10",
    "coenzyme q10": "Coenzyme Q10",
    "ubiquinol": "Coenzyme Q10",
    "ubiquinone": "Coenzyme Q10",
    "melatonin": "Melatonin",
    "collagen": "Collagen",
    "collagen peptides": "Collagen",
    "hydrolyzed collagen": "Collagen",
    "creatine": "Creatine",
    "creatine monohydrate": "Creatine",
    "probiotics": "Probiotic Blend",
    "lactobacillus": "Probiotic Blend",
    "bifidobacterium": "Probiotic Blend",
}

_FUZZY_THRESHOLD = 85


def resolve(ingredient_name: str, db_path: Path | None = None) -> dict:
    """
    Resolve ingredient name → canonical record via 3 stages.
    Returns a dict with canonical_id, canonical_name, match_method, confidence, resolution_failed.
    Never raises.
    """
    db_path = db_path or _DB_PATH
    query = ingredient_name.strip() if ingredient_name else ""
    if not query:
        return _failed(query, "empty_query")

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Stage 1: exact case-insensitive match
        row = conn.execute(
            "SELECT Id, Name FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
            (query,),
        ).fetchone()
        if row:
            conn.close()
            return _ok(row["Id"], row["Name"], "exact", 1.0, query)

        # Stage 2: curated synonym map
        normalized = query.lower().strip()
        if normalized in _SYNONYMS:
            canonical_name = _SYNONYMS[normalized]
            row = conn.execute(
                "SELECT Id, Name FROM Ingredient_Canonical WHERE LOWER(Name) = LOWER(?) LIMIT 1",
                (canonical_name,),
            ).fetchone()
            if row:
                conn.close()
                return _ok(row["Id"], row["Name"], "synonym", 0.95, query)

        # Stage 3: RapidFuzz token_set_ratio over all canonicals
        all_rows = conn.execute("SELECT Id, Name FROM Ingredient_Canonical").fetchall()
        conn.close()

        best_score = 0
        best_row = None
        for r in all_rows:
            score = fuzz.token_set_ratio(query.lower(), r["Name"].lower())
            if score > best_score:
                best_score = score
                best_row = r

        if best_score >= _FUZZY_THRESHOLD and best_row:
            return _ok(best_row["Id"], best_row["Name"], "fuzzy", min(0.85, best_score / 100.0), query)

        return _failed(query, "no_match")

    except Exception as exc:
        return _failed(query, f"db_error:{exc}")


def _ok(canonical_id: int, canonical_name: str, method: str, confidence: float, query: str) -> dict:
    return {
        "canonical_id": canonical_id,
        "canonical_name": canonical_name,
        "match_method": method,
        "confidence": confidence,
        "resolution_failed": False,
        "query": query,
    }


def _failed(query: str, reason: str) -> dict:
    return {
        "canonical_id": None,
        "canonical_name": None,
        "match_method": "unresolved",
        "confidence": 0.0,
        "resolution_failed": True,
        "query": query,
        "reason": reason,
    }
