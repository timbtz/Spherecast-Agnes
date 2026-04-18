"""Fix Ingredient_Substitution_Rule Name_A/Name_B to match Ingredient_Canonical.Name exactly."""
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.fix_substitution_rules")

ALIAS_TABLE = {
    "ascorbic acid": "Vitamin C",
    "cholecalciferol": "Vitamin D",
    "d-alpha tocopherol": "Tocopherols",
    "dl-alpha tocopherol": "Tocopherols",
    "mixed tocopherols": "Tocopherols",
    "methylfolate": "Folate",
    "5-mthf": "Folate",
    "cyanocobalamin": "vitamin B12",
    "magnesium oxide": "Magnesia",
    "magnesium citrate": "Trimagnesium dicitrate",
    "hydroxypropyl methylcellulose": "Hypromellose",
    "hpmc": "Hypromellose",
    "dextrose": "D-Glucopyranose",
    "glucose": "D-Glucopyranose",
    "coq10": "Coenzyme Q10",
    "potassium citrate": "potassium citrate monohydrate",
    "vegetarian capsule": "Vegan Capsule",
}


def fix_name(name: str, canonical_set: set[str]) -> tuple[str, str]:
    """Returns (new_name, status) where status is 'updated'|'already_correct'|'unresolved'."""
    if name.lower() in canonical_set:
        return name, "already_correct"
    alias = ALIAS_TABLE.get(name.lower())
    if alias and alias.lower() in canonical_set:
        return alias, "updated"
    return name, "unresolved"


def run() -> None:
    conn = sqlite3.connect(str(ENRICHED_DB))

    canonical_names = {
        r[0].lower() for r in conn.execute("SELECT Name FROM Ingredient_Canonical").fetchall()
    }

    rules = conn.execute(
        "SELECT Id, Name_A, Name_B FROM Ingredient_Substitution_Rule"
    ).fetchall()

    logger.info(f"Processing {len(rules)} substitution rules")

    updated = already_correct = unresolved = 0

    for rule_id, name_a, name_b in rules:
        new_a, status_a = fix_name(name_a, canonical_names)
        new_b, status_b = fix_name(name_b, canonical_names)

        if status_a == "updated" or status_b == "updated":
            conn.execute(
                "UPDATE Ingredient_Substitution_Rule SET Name_A = ?, Name_B = ? WHERE Id = ?",
                (new_a, new_b, rule_id),
            )
            logger.info(f"  Updated rule {rule_id}: '{name_a}'→'{new_a}', '{name_b}'→'{new_b}'")
            updated += 1
        elif status_a == "unresolved" or status_b == "unresolved":
            unresolved_side = []
            if status_a == "unresolved":
                unresolved_side.append(name_a)
            if status_b == "unresolved":
                unresolved_side.append(name_b)
            logger.debug(f"  Unresolved rule {rule_id}: {unresolved_side}")
            unresolved += 1
        else:
            already_correct += 1

    conn.commit()
    conn.close()

    logger.info(
        f"Done — updated: {updated}, already_correct: {already_correct}, unresolved: {unresolved}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    run()
