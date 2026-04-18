"""Heuristic Grade_Flag classifier — no API required."""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.grade_classifier")

FLAVOR_KEYWORDS = ["flavor", "flavour", "artificial flavor", "natural flavor"]
SWEETENER_NAMES = ["sucralose", "erythritol", "sorbitol", "stevia", "monk fruit",
                   "sucrose", "xylitol", "maltitol", "saccharin", "aspartame",
                   "rebaudioside", "coconut sugar", "tapioca syrup"]
EXCIPIENT_KEYWORDS = ["cellulose", "silicon dioxide", "magnesium stearate", "croscarmellose",
                      "hpmc", "hypromellose", "methylcellulose", "talc", "silica",
                      "hydroxypropyl", "carrageenan", "carnauba", "shellac",
                      "titanium dioxide", "rice flour", "polyethylene glycol",
                      "crospovidone", "stearic acid", "starch", "polydextrose",
                      "pharmaceutical glaze", "sodium benzoate", "sorbic acid",
                      "alginate", "sodium alginate", "citric acid",
                      "capsule", "gum", "coating", "base of"]
FOOD_KEYWORDS = ["protein", "gelatin", "collagen", "maltodextrin", "inulin",
                 "lecithin", "pectin", "xanthan", "guar gum", "sunflower oil",
                 "coconut oil", "mct", "medium chain triglycerides", "cocoa", "whey",
                 "casein", "rice bran", "flax", "pumpkin", "hemp",
                 "beet", "kale", "olive", "palm", "safflower", "coconut",
                 "orange", "lemon", "pomegranate", "grape", "soy",
                 "ginger", "turmeric", "cayenne", "cinnamon", "pepper",
                 "acacia", "salt", "corn", "spleen", "fruit", "vegetable juice",
                 "alfalfa", "algae", "kelp", "spirulina"]
SUPPLEMENT_KEYWORDS = ["vitamin", "zinc", "magnesium", "calcium", "iron", "potassium",
                       "selenium", "chromium", "copper", "manganese", "iodine",
                       "cobalamin", "folate", "biotin", "niacin", "thiamin", "riboflavin",
                       "pantothenic", "folic acid",
                       "probiotic", "bifido", "lactobacillus", "enzyme",
                       "green tea", "bioflavonoid", "rhodiola", "boswellia",
                       "yeast", "trace mineral", "coenzyme", "ashwagandha",
                       "elderberry", "echinacea", "quercetin", "resveratrol",
                       "berberine", "curcumin", "omega", "fish oil", "krill"]
AMINO_ACID_NAMES = ["glycine", "lysine", "leucine", "isoleucine", "valine", "methionine",
                    "phenylalanine", "tryptophan", "threonine", "histidine", "arginine",
                    "glutamine", "taurine", "carnitine", "creatine", "beta-alanine",
                    "citrulline", "l-leucine", "l-valine", "l-isoleucine"]


def classify_grade(name: str, smiles: str | None) -> tuple[str, float]:
    n = name.lower()
    if any(kw in n for kw in FLAVOR_KEYWORDS):
        return "flavor", 0.9
    if any(kw in n for kw in SWEETENER_NAMES):
        return "sweetener", 0.9
    if any(kw in n for kw in EXCIPIENT_KEYWORDS):
        return "excipient", 0.9
    if any(kw in n for kw in FOOD_KEYWORDS):
        return "food", 0.9
    if any(kw in n for kw in SUPPLEMENT_KEYWORDS):
        return "supplement", 0.9
    if any(kw in n for kw in AMINO_ACID_NAMES):
        return "supplement", 0.9
    if smiles is not None:
        return "supplement", 0.7
    return "unknown", 0.0


class GradeClassifier:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT Id, Name, SMILES FROM Ingredient_Canonical").fetchall()
        conn.close()

        logger.info(f"Classifying {len(rows)} canonical ingredients")
        counts: dict[str, int] = {}

        for canonical_id, name, smiles in rows:
            grade, _ = classify_grade(name, smiles)
            counts[grade] = counts.get(grade, 0) + 1
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE Ingredient_Canonical SET Grade_Flag = ? WHERE Id = ?",
                (grade, canonical_id),
            )
            conn.commit()
            conn.close()

        logger.info(f"Grade_Flag distribution: {counts}")
        unknown = counts.get("unknown", 0)
        logger.info(f"Unknown count: {unknown} / {len(rows)}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    GradeClassifier().run()
