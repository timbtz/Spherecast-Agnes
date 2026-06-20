"""Directory adapters for supplier discovery.

Each adapter returns a list of candidate supplier dicts:
    {
        "supplier_name": str,
        "country_code": str|None,
        "source_url": str|None,
        "certifications_raw": str|None,   # raw text we'll parse later
    }

Adapters MUST be polite (rate-limited) and respect robots.txt — Tim's
playwright runner already handles that for the directories we care
about; we just supply the URLs and parsers.

For the hackathon demo we ship two real adapters (Thomasnet open search,
NIH DSLD label-issuer) and a SEED adapter that returns a deterministic
fixture so the demo runs even with no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


# ----- helpers -------------------------------------------------------------

def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


# ----- seed (offline) ------------------------------------------------------

_SEED_FIXTURE: Dict[str, List[Dict]] = {
    "sucralose": [
        {
            "supplier_name": "JK Sucralose Inc.",
            "country_code": "CN",
            "source_url": "fixture://seed/jksucralose",
            "certifications_raw": "FSSC 22000; ISO 9001; Kosher; Halal",
        },
        {
            "supplier_name": "Niutang Chemical",
            "country_code": "CN",
            "source_url": "fixture://seed/niutang",
            "certifications_raw": "ISO 22000; FCC; Kosher",
        },
        {
            "supplier_name": "Tate & Lyle (Splenda)",
            "country_code": "US",
            "source_url": "fixture://seed/tate-lyle",
            "certifications_raw": "FSSC 22000; SQF Level 3; USP monograph",
        },
    ],
    "stevia": [
        {
            "supplier_name": "PureCircle",
            "country_code": "MY",
            "source_url": "fixture://seed/purecircle",
            "certifications_raw": "FSSC 22000; Non-GMO Project Verified",
        },
        {
            "supplier_name": "GLG Life Tech",
            "country_code": "CN",
            "source_url": "fixture://seed/glg",
            "certifications_raw": "ISO 22000; Kosher",
        },
    ],
    "magnesium citrate": [
        {
            "supplier_name": "Jost Chemical",
            "country_code": "US",
            "source_url": "fixture://seed/jost",
            "certifications_raw": "USP; FCC; ISO 9001",
        },
        {
            "supplier_name": "Dr. Paul Lohmann",
            "country_code": "DE",
            "source_url": "fixture://seed/lohmann",
            "certifications_raw": "EP; USP; ISO 22000",
        },
    ],
}


def seed_directory(canonical_name: str) -> List[Dict]:
    """Offline fixture so the demo runs without hitting the network."""
    rows = _SEED_FIXTURE.get((canonical_name or "").strip().lower(), [])
    out = []
    for r in rows:
        c = dict(r)
        c["supplier_name"] = _normalize_name(c["supplier_name"])
        c["source_directory"] = "seed"
        out.append(c)
    return out


# ----- thomasnet ------------------------------------------------------------

def thomasnet_directory(canonical_name: str, fetch_html=None) -> List[Dict]:
    """Thomasnet open search adapter.

    `fetch_html` is injected so this stays unit-testable. Tim's playwright
    runner provides the real fetcher in production. If `fetch_html` is
    None we fall back to seed (no silent network calls in tests).
    """
    if fetch_html is None:
        return [dict(r, source_directory="thomasnet:fallback-seed") for r in seed_directory(canonical_name)]

    html = fetch_html(f"https://www.thomasnet.com/suppliers/{canonical_name.replace(' ', '-')}")
    return _parse_thomasnet_html(html, canonical_name)


def _parse_thomasnet_html(html: str, canonical_name: str) -> List[Dict]:
    # Lightweight extractor — production version uses BeautifulSoup.
    out: List[Dict] = []
    for match in re.finditer(r'data-supplier-name="([^"]+)".*?data-country="([^"]*)"', html or ""):
        out.append(
            {
                "supplier_name": _normalize_name(match.group(1)),
                "country_code": match.group(2) or None,
                "source_url": "https://www.thomasnet.com/",
                "certifications_raw": None,
                "source_directory": "thomasnet",
            }
        )
    return out


# ----- DSLD ----------------------------------------------------------------

def dsld_label_issuers(canonical_name: str, fetch_json=None) -> List[Dict]:
    """NIH Dietary Supplement Label DB — pulls label issuers (= supplement
    brands) that list this ingredient. Useful for the supplement leg.
    """
    if fetch_json is None:
        return [dict(r, source_directory="dsld:fallback-seed") for r in seed_directory(canonical_name)]

    payload = fetch_json(
        f"https://api.ods.od.nih.gov/dsld/v9/search-filter?q={canonical_name}"
    )
    out: List[Dict] = []
    for item in (payload or {}).get("hits", []):
        brand = _normalize_name(item.get("brand", ""))
        if not brand:
            continue
        out.append(
            {
                "supplier_name": brand,
                "country_code": item.get("countryCode"),
                "source_url": item.get("url"),
                "certifications_raw": json.dumps(item.get("certifications", [])),
                "source_directory": "dsld",
            }
        )
    return out


# ----- registry ------------------------------------------------------------

DIRECTORIES = {
    "seed": seed_directory,
    "thomasnet": thomasnet_directory,
    "dsld": dsld_label_issuers,
}


def list_supported() -> List[str]:
    return sorted(DIRECTORIES.keys())


def load_user_seed(path: Optional[Path]) -> Dict[str, List[Dict]]:
    """Optional user-supplied seed file (jsonl) so Tim/eng can extend
    fixtures without editing this module."""
    if not path or not Path(path).exists():
        return {}
    out: Dict[str, List[Dict]] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        key = (rec.get("canonical_name") or "").strip().lower()
        out.setdefault(key, []).append(rec)
    return out
