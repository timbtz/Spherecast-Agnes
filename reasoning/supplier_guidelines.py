"""Supplier intelligence wiki reader — injects grade-level guidelines into scoring context."""
from pathlib import Path

_WIKI_DIR = Path(__file__).parent.parent / "Orchestration" / "Data" / "supplier_wiki"

_GRADE_TO_FILE = {
    "supplement": "supplements.md",
    "excipient": "excipients.md",
    "food": "food.md",
    "sweetener": "food.md",
    "flavor": "food.md",
    "unknown": "supplements.md",
}


def get_guidelines(grade: str | None) -> str:
    """Return markdown guidelines text for the given ingredient grade, or empty string."""
    fname = _GRADE_TO_FILE.get((grade or "unknown").lower(), "supplements.md")
    fpath = _WIKI_DIR / fname
    if fpath.exists():
        return fpath.read_text(encoding="utf-8")
    return ""
