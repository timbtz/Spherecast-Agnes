"""ISO-3166 country allow-list + normalization.

Small hand-curated set that covers the supplier landscape we actually see
(pharma APIs, botanicals, commodity excipients). For anything outside this
list we return None and the caller should WARN + store NULL.

We accept short-form ISO-2 / ISO-3 and common full names (with minor spelling
variants). Whitespace and case are normalized on input.
"""
from __future__ import annotations
import re

# canonical ISO-2 → human short form we persist in Country_Origin.
_ISO2_TO_DISPLAY: dict[str, str] = {
    "US": "USA",    "CA": "Canada",     "MX": "Mexico",
    "GB": "UK",     "IE": "Ireland",    "FR": "France",
    "DE": "Germany","IT": "Italy",      "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland",
    "AT": "Austria","SE": "Sweden",     "DK": "Denmark",
    "NO": "Norway", "FI": "Finland",    "PL": "Poland",
    "CZ": "Czechia","SK": "Slovakia",   "HU": "Hungary",
    "RO": "Romania","BG": "Bulgaria",   "GR": "Greece",
    "PT": "Portugal","LU": "Luxembourg","IS": "Iceland",
    "LI": "Liechtenstein",
    "IN": "India",  "CN": "China",      "JP": "Japan",
    "KR": "South Korea", "TW": "Taiwan","HK": "Hong Kong",
    "SG": "Singapore", "MY": "Malaysia","TH": "Thailand",
    "VN": "Vietnam","ID": "Indonesia",  "PH": "Philippines",
    "AU": "Australia", "NZ": "New Zealand",
    "IL": "Israel", "AE": "UAE",        "SA": "Saudi Arabia",
    "TR": "Turkey", "EG": "Egypt",      "ZA": "South Africa",
    "BR": "Brazil", "AR": "Argentina",  "CL": "Chile",
    "CO": "Colombia", "PE": "Peru",
    "RU": "Russia", "UA": "Ukraine",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka",
}

# Aliases for input → ISO-2. Order matters: longer/more-specific first. Keys
# are upper-cased, punctuation-stripped.
_ALIASES_TO_ISO2: dict[str, str] = {
    # Variations on USA
    "USA": "US", "US": "US", "U.S.": "US", "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US", "AMERICA": "US",
    # UK / GB
    "UK": "GB", "GB": "GB", "GREAT BRITAIN": "GB", "UNITED KINGDOM": "GB",
    "ENGLAND": "GB", "SCOTLAND": "GB", "WALES": "GB",
    # Canada
    "CANADA": "CA", "CA": "CA", "CAN": "CA",
    # Germany
    "GERMANY": "DE", "DE": "DE", "DEU": "DE",
    # France
    "FRANCE": "FR", "FR": "FR", "FRA": "FR",
    # China
    "CHINA": "CN", "CN": "CN", "CHN": "CN", "PRC": "CN",
    "PEOPLE'S REPUBLIC OF CHINA": "CN",
    # India
    "INDIA": "IN", "IN": "IN", "IND": "IN",
    # Japan
    "JAPAN": "JP", "JP": "JP", "JPN": "JP",
    # Italy
    "ITALY": "IT", "IT": "IT", "ITA": "IT",
    # Spain
    "SPAIN": "ES", "ES": "ES", "ESP": "ES",
    # Netherlands
    "NETHERLANDS": "NL", "NL": "NL", "NLD": "NL", "HOLLAND": "NL",
    "THE NETHERLANDS": "NL",
    # Switzerland
    "SWITZERLAND": "CH", "CH": "CH", "CHE": "CH",
    # Belgium
    "BELGIUM": "BE", "BE": "BE", "BEL": "BE",
    # Sweden / Denmark / Norway / Finland
    "SWEDEN": "SE", "SE": "SE",
    "DENMARK": "DK", "DK": "DK",
    "NORWAY": "NO", "NO": "NO",
    "FINLAND": "FI", "FI": "FI",
    # Asia
    "SOUTH KOREA": "KR", "KOREA": "KR", "REPUBLIC OF KOREA": "KR",
    "KR": "KR", "ROK": "KR",
    "TAIWAN": "TW", "TW": "TW",
    "HONG KONG": "HK", "HK": "HK",
    "SINGAPORE": "SG", "SG": "SG",
    "MALAYSIA": "MY", "MY": "MY",
    "THAILAND": "TH", "TH": "TH",
    "VIETNAM": "VN", "VIET NAM": "VN", "VN": "VN",
    "INDONESIA": "ID", "ID": "ID",
    "PHILIPPINES": "PH", "PH": "PH",
    # Oceania
    "AUSTRALIA": "AU", "AU": "AU", "AUS": "AU",
    "NEW ZEALAND": "NZ", "NZ": "NZ",
    # Middle East / Africa
    "ISRAEL": "IL", "IL": "IL",
    "UAE": "AE", "UNITED ARAB EMIRATES": "AE", "AE": "AE",
    "SAUDI ARABIA": "SA", "SA": "SA",
    "TURKEY": "TR", "TR": "TR", "TURKIYE": "TR",
    "EGYPT": "EG", "EG": "EG",
    "SOUTH AFRICA": "ZA", "ZA": "ZA", "RSA": "ZA",
    # LATAM
    "BRAZIL": "BR", "BRASIL": "BR", "BR": "BR",
    "ARGENTINA": "AR", "AR": "AR",
    "CHILE": "CL", "CL": "CL",
    "COLOMBIA": "CO", "CO": "CO",
    "MEXICO": "MX", "MX": "MX",
    "PERU": "PE", "PE": "PE",
    # Eastern Europe
    "POLAND": "PL", "PL": "PL",
    "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ", "CZ": "CZ",
    "SLOVAKIA": "SK", "SK": "SK",
    "HUNGARY": "HU", "HU": "HU",
    "ROMANIA": "RO", "RO": "RO",
    "BULGARIA": "BG", "BG": "BG",
    "GREECE": "GR", "GR": "GR",
    "PORTUGAL": "PT", "PT": "PT",
    # Others
    "RUSSIA": "RU", "RU": "RU", "RUSSIAN FEDERATION": "RU",
    "UKRAINE": "UA", "UA": "UA",
    "IRELAND": "IE", "IE": "IE",
    "AUSTRIA": "AT", "AT": "AT",
    "LUXEMBOURG": "LU", "LU": "LU",
    "LIECHTENSTEIN": "LI", "LI": "LI",
    "ICELAND": "IS", "IS": "IS",
    "PAKISTAN": "PK", "PK": "PK",
    "BANGLADESH": "BD", "BD": "BD",
    "SRI LANKA": "LK", "LK": "LK",
}


def normalize_country(raw: str | None) -> str | None:
    """Validate against ISO-3166 allow-list. Returns display form or None.

    None is returned for: empty input, unrecognised string, multi-country
    strings that don't resolve cleanly. Caller should store NULL + WARN.
    """
    if not raw:
        return None
    s = str(raw).strip()
    # Strip parentheticals: "USA (inferred)" → "USA"
    s = re.split(r"[(\[]", s)[0].strip()
    if not s:
        return None
    # Normalise whitespace + case, strip periods everywhere (handles "U.S.")
    s = re.sub(r"\s+", " ", s).upper().replace(".", "")
    # Drop surrounding punctuation
    s = s.strip(",;:!? ")
    iso2 = _ALIASES_TO_ISO2.get(s)
    if iso2:
        return _ISO2_TO_DISPLAY[iso2]
    # Try first-separator-split (e.g. "USA, Germany" or "USA; Germany" → "USA")
    head = re.split(r"[,;/&+|]", s)[0].strip()
    iso2 = _ALIASES_TO_ISO2.get(head)
    if iso2:
        return _ISO2_TO_DISPLAY[iso2]
    # Try first-token only ("USA Missouri" → "USA")
    first = head.split()[0] if head else ""
    iso2 = _ALIASES_TO_ISO2.get(first)
    if iso2:
        return _ISO2_TO_DISPLAY[iso2]
    return None


def is_valid_country(raw: str | None) -> bool:
    """True if raw resolves to a known country."""
    return normalize_country(raw) is not None
