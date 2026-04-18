"""Parse raw-material SKU slugs into human-readable ingredient names.

SKU format: RM-C{companyId}-{ingredient-slug}-{8-hex-hash}
Example:    RM-C30-magnesium-stearate-201fdf47  →  "magnesium stearate"
"""
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

SKU_PATTERN = re.compile(r"^RM-C(\d+)-(.+)-([0-9a-f]{8})$", re.IGNORECASE)

# Common abbreviations found in slugs → expanded form.
# Applied to the raw slug (before dash→space) so hyphens act as word boundaries.
# Ordered: longer/more specific patterns first to prevent partial matches.
SLUG_EXPANSIONS: list[tuple[str, str]] = [
    (r"\bcoq-?10\b", "coenzyme q10"),            # coq10 before q10
    (r"\b5-mthf\b", "methylfolate"),
    (r"\balpha-gpc\b", "alpha glycerylphosphorylcholine"),
    (r"\balcar\b", "acetyl l-carnitine"),
    (r"\bvit\b", "vitamin"),
    (r"\bmcc\b", "microcrystalline cellulose"),
    (r"\bhpmc\b", "hydroxypropyl methylcellulose"),
    (r"\bnac\b", "n-acetyl cysteine"),
    (r"\bfos\b", "fructooligosaccharides"),
    (r"\behc\b", "egcg"),
]

# Slug fragments that indicate an ingredient is a proprietary blend or non-normalizable
COMPLEX_MARKERS = frozenset(["complex", "blend", "mix", "proprietary", "natural-flavor",
                              "natural-flavour", "other-ingredient", "excipient"])


@dataclass
class ParsedSKU:
    sku: str
    product_id: int
    company_id: int
    slug: str
    extracted_name: str
    hash_suffix: str
    is_complex: bool  # True if ingredient is a proprietary blend/complex


def _dedup_words(words: list[str]) -> list[str]:
    """Remove consecutive duplicate single words and exact repeated phrases."""
    # Remove consecutive duplicate words
    result = [w for i, w in enumerate(words) if i == 0 or w.lower() != words[i - 1].lower()]
    # Remove exact phrase repetition: [a,b,c,a,b,c] → [a,b,c]
    n = len(result)
    for length in range(n // 2, 0, -1):
        if result[:length] == [w.lower() for w in result[:length]] and \
           [w.lower() for w in result[:length]] == [w.lower() for w in result[length:2 * length]]:
            return result[:length]
    return result


def parse_sku(sku: str, product_id: int = 0) -> ParsedSKU | None:
    """Extract ingredient name from a raw-material SKU string."""
    m = SKU_PATTERN.match(sku.strip())
    if not m:
        return None

    company_id = int(m.group(1))
    slug = m.group(2)
    hash_suffix = m.group(3)
    extracted_name = _slug_to_name(slug)
    is_complex = any(marker in slug.lower() for marker in COMPLEX_MARKERS)

    return ParsedSKU(
        sku=sku,
        product_id=product_id,
        company_id=company_id,
        slug=slug,
        extracted_name=extracted_name,
        hash_suffix=hash_suffix,
        is_complex=is_complex,
    )


def _slug_to_name(slug: str) -> str:
    """Convert a hyphen-separated slug to a normalised, human-readable ingredient name."""
    # Apply expansions on the hyphened slug first (hyphens serve as word boundaries)
    name = slug
    for pattern, expansion in SLUG_EXPANSIONS:
        name = re.sub(pattern, expansion, name, flags=re.IGNORECASE)
    # Replace remaining hyphens with spaces
    name = name.replace("-", " ").strip()
    words = name.split()
    return " ".join(_dedup_words(words))


def parse_all_raw_material_skus(db_path: str | Path) -> list[ParsedSKU]:
    """Return ParsedSKU for every raw-material Product row in db_enriched.sqlite."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT Id, SKU FROM Product WHERE Type = 'raw-material'"
    ).fetchall()
    conn.close()

    results: list[ParsedSKU] = []
    for product_id, sku in rows:
        parsed = parse_sku(sku, product_id=product_id)
        if parsed:
            results.append(parsed)
    return results
