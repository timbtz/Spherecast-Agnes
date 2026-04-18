"""Heuristic role/function classifier — no API required.
Populates Ingredient_Canonical.Function for all rows.
Values: lubricant | mineral-fortificant | vitamin-fortificant | antioxidant |
        sweetener | high-intensity-sweetener | acidulant | preservative |
        emulsifier | thickener | stabilizer | colorant | functional-stimulant |
        functional-amino | functional-performance | protein-source | unknown
"""
import logging
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"

logger = logging.getLogger("agnes.role_classifier")

# Copied verbatim from reasoning/role_inferrer.py ROLE_RULES
ROLE_RULES: dict = {
    "citric acid": "acidulant",
    "malic acid": "acidulant",
    "lactic acid": "acidulant",
    "phosphoric acid": "acidulant",
    "ascorbic acid": "antioxidant",
    "tartaric acid": "acidulant",
    "sucrose": "sweetener",
    "glucose": "sweetener",
    "fructose": "sweetener",
    "high fructose corn syrup": "sweetener",
    "honey": "sweetener",
    "sucralose": "high-intensity-sweetener",
    "aspartame": "high-intensity-sweetener",
    "stevia": "high-intensity-sweetener",
    "rebaudioside a": "high-intensity-sweetener",
    "monk fruit extract": "high-intensity-sweetener",
    "potassium sorbate": "preservative",
    "sodium benzoate": "preservative",
    "calcium propionate": "preservative",
    "beta carotene": "colorant",
    "annatto": "colorant",
    "caramel color": "colorant",
    "anthocyanin": "colorant",
    "lecithin": "emulsifier",
    "soy lecithin": "emulsifier",
    "sunflower lecithin": "emulsifier",
    "xanthan gum": "thickener",
    "guar gum": "thickener",
    "pectin": "thickener",
    "carrageenan": "stabilizer",
    "gum arabic": "stabilizer",
    "magnesium oxide": "mineral-fortificant",
    "magnesium citrate": "mineral-fortificant",
    "magnesium stearate": "lubricant",
    "vegetable magnesium stearate": "lubricant",
    "calcium stearate": "lubricant",
    "stearic acid": "lubricant",
    "zinc gluconate": "mineral-fortificant",
    "calcium carbonate": "mineral-fortificant",
    "cyanocobalamin": "vitamin-fortificant",
    "methylcobalamin": "vitamin-fortificant",
    "cholecalciferol": "vitamin-fortificant",
    "alpha-tocopherol": "antioxidant",
    "caffeine": "functional-stimulant",
    "l-theanine": "functional-amino",
    "creatine monohydrate": "functional-performance",
    "whey protein isolate": "protein-source",
    "pea protein isolate": "protein-source",
}

# Additional keyword patterns for broader coverage
_LUBRICANT_KEYWORDS = ["stearate", "stearic", "talc", "wax"]
_MINERAL_KEYWORDS = ["zinc", "magnesium", "calcium", "iron", "potassium", "selenium",
                     "chromium", "copper", "manganese", "iodine", "molybdenum", "boron"]
_VITAMIN_KEYWORDS = ["vitamin", "cobalamin", "folate", "folic acid", "biotin", "niacin",
                     "thiamin", "riboflavin", "pantothenic", "tocopherol", "retinol",
                     "cholecalciferol", "ergocalciferol", "ascorbic"]
_SWEETENER_KEYWORDS = ["erythritol", "sorbitol", "xylitol", "maltitol", "saccharin",
                       "rebaudioside", "monk fruit", "acesulfame"]
_PROTEIN_KEYWORDS = ["protein", "whey", "casein", "collagen", "gelatin", "albumin"]
_EMULSIFIER_KEYWORDS = ["lecithin", "mono- and diglycerides", "polyglycerol", "polysorbate"]
_THICKENER_KEYWORDS = ["cellulose", "gum", "pectin", "starch", "dextrin", "inulin",
                       "carrageenan", "alginate", "agar"]
_PRESERVATIVE_KEYWORDS = ["sorbate", "benzoate", "propionate", "ascorbate"]
_COLORANT_KEYWORDS = ["carotene", "annatto", "caramel", "anthocyanin", "lycopene",
                      "chlorophyll", "beet", "turmeric", "color", "colour"]
_ACIDULANT_KEYWORDS = ["acid", "lactate", "tartrate", "fumarate", "acetate"]
_ANTIOXIDANT_KEYWORDS = ["tocopherol", "bha", "bht", "rosemary extract", "ascorbyl",
                         "astaxanthin", "coenzyme q10", "ubiquinol", "ubiquinone",
                         "lutein", "lycopene", "zeaxanthin", "resveratrol", "quercetin"]
_EXCIPIENT_KEYWORDS = ["silicon dioxide", "hydroxypropyl", "hypromellose", "croscarmellose",
                       "povidone", "crospovidone", "shellac", "titanium dioxide",
                       "polyethylene glycol", "polydextrose", "microcrystalline",
                       "capsule", "coating", "base of", "pharmaceutical glaze"]
_AMINO_KEYWORDS = ["l-leucine", "l-valine", "l-isoleucine", "l-lysine", "l-arginine",
                   "l-glutamine", "l-histidine", "l-methionine", "l-phenylalanine",
                   "l-threonine", "l-tryptophan", "l-tyrosine", "l-alanine",
                   "l-cysteine", "l-serine", "l-proline", "beta-alanine",
                   "taurine", "l-theanine", "l-carnitine", "acetyl-l-carnitine",
                   "glycine", "lysine", "leucine", "valine", "isoleucine",
                   "glutamine", "citrulline", "ornithine", "arginine"]
_PROBIOTIC_KEYWORDS = ["lactobacillus", "bifidobacterium", "streptococcus thermophilus",
                       "saccharomyces", "bacillus coagulans", "probiotic", "cfu"]
_ENZYME_KEYWORDS = ["enzyme", "amylase", "protease", "lipase", "lactase", "cellulase",
                    "bromelain", "papain", "pepsin"]
_BOTANICAL_KEYWORDS = ["extract", "leaf", "root", "bark", "berry", "seed extract",
                       "herb", "botanical", "powder", "ashwagandha", "rhodiola",
                       "echinacea", "elderberry", "ginkgo", "ginseng", "turmeric",
                       "curcumin", "boswellia", "berberine", "black pepper",
                       "green tea", "grape seed", "milk thistle", "saw palmetto",
                       "valerian", "cinnamon", "cayenne", "ginger", "garlic",
                       "spirulina", "chlorella", "kelp", "algae", "alfalfa",
                       "kale", "beet", "citrus", "bioflavonoid", "quercetin",
                       "resveratrol", "lutein", "astaxanthin", "lycopene",
                       "coenzyme q10", "q10", "ubiquinol", "alpha lipoic",
                       "corn silk", "green onion"]


def classify_role(name: str) -> tuple[str, float]:
    n = name.strip().lower()

    # Direct lookup first (highest confidence)
    if n in ROLE_RULES:
        return ROLE_RULES[n], 0.9

    # Keyword-based fallbacks
    if any(kw in n for kw in _LUBRICANT_KEYWORDS):
        return "lubricant", 0.8
    if any(kw in n for kw in _EXCIPIENT_KEYWORDS):
        return "excipient", 0.8
    if any(kw in n for kw in _VITAMIN_KEYWORDS):
        return "vitamin-fortificant", 0.8
    if any(kw in n for kw in _MINERAL_KEYWORDS):
        return "mineral-fortificant", 0.8
    if any(kw in n for kw in _SWEETENER_KEYWORDS):
        return "sweetener", 0.8
    if any(kw in n for kw in _PROTEIN_KEYWORDS):
        return "protein-source", 0.8
    if any(kw in n for kw in _EMULSIFIER_KEYWORDS):
        return "emulsifier", 0.8
    if any(kw in n for kw in _THICKENER_KEYWORDS):
        return "thickener", 0.7
    if any(kw in n for kw in _ANTIOXIDANT_KEYWORDS):
        return "antioxidant", 0.75
    if any(kw in n for kw in _COLORANT_KEYWORDS):
        return "colorant", 0.75
    if any(kw in n for kw in _PRESERVATIVE_KEYWORDS):
        return "preservative", 0.75
    if any(kw in n for kw in _AMINO_KEYWORDS):
        return "functional-amino", 0.8
    if any(kw in n for kw in _PROBIOTIC_KEYWORDS):
        return "probiotic", 0.85
    if any(kw in n for kw in _ENZYME_KEYWORDS):
        return "enzyme", 0.85
    if any(kw in n for kw in _BOTANICAL_KEYWORDS):
        return "functional-botanical", 0.7
    if any(kw in n for kw in _ANTIOXIDANT_KEYWORDS):
        return "antioxidant", 0.75
    if any(kw in n for kw in _COLORANT_KEYWORDS):
        return "colorant", 0.75
    if any(kw in n for kw in _PRESERVATIVE_KEYWORDS):
        return "preservative", 0.75
    if any(kw in n for kw in _ACIDULANT_KEYWORDS):
        return "acidulant", 0.65

    return "unknown", 0.0


class RoleClassifier:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT Id, Name FROM Ingredient_Canonical").fetchall()
        conn.close()

        logger.info(f"Classifying {len(rows)} canonical ingredients")
        counts: dict[str, int] = {}

        for canonical_id, name in rows:
            role, _ = classify_role(name)
            counts[role] = counts.get(role, 0) + 1
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE Ingredient_Canonical SET Function = ? WHERE Id = ?",
                (role, canonical_id),
            )
            conn.commit()
            conn.close()

        logger.info(f"Function distribution: {counts}")
        unknown = counts.get("unknown", 0)
        logger.info(f"Unknown count: {unknown} / {len(rows)}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    RoleClassifier().run()
