"""Async enricher: discovers bulk ingredient suppliers via Google Search → Supplier_Commercial."""
import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()

from enrichment.enrichers.country_iso import normalize_country as iso_normalize_country

ROOT = Path(__file__).parent.parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.supplier_web_enricher")

_CONFIDENCE_WEB = 0.65
_EVIDENCE_MAX_LEN = 200

# Field-name aliases — the model sometimes free-styles these even when the
# system prompt pins the schema. Try each in order.
_PRICE_KEYS = ("price_range_usd_per_kg", "price_range", "price", "price_usd",
               "price_per_kg", "unit_price")
_MOQ_KEYS = ("moq_range_kg", "moq", "minimum_order", "minimum_order_quantity",
             "min_order_kg")
_URL_KEYS = ("website", "contact_website", "url", "product_url", "source_url",
             "link")
_CERT_KEYS = ("certifications", "certs", "certificates", "certification")
_GRADE_KEYS = ("grade", "purity", "spec", "specification")
_EVIDENCE_KEYS = ("evidence_snippet", "evidence", "snippet", "quote",
                  "source_snippet", "notes")

# Known hostname → URL archetype.
# Archetypes are used to:
#   (a) segment pricing (lab-reagent prices are $/g; bulk distributor prices
#       are $/kg — comparing them directly is bogus, see outlier QC)
#   (b) set Provenance_Confidence correctly (manufacturer_direct is the
#       strongest signal, directory listings are weaker)
# Anything not in this table defaults to 'unknown' — we prefer unknown over
# mislabeling. Host-matching is done via parent-domain walk.
_ARCHETYPE_HOSTS: dict[str, str] = {
    # Directory listings / B2B marketplaces — quotes from various suppliers
    "indiamart.com":       "directory_listing",
    "made-in-china.com":   "directory_listing",
    "alibaba.com":         "directory_listing",
    "echemi.com":          "directory_listing",
    "tradewheel.com":      "directory_listing",
    "globalsources.com":   "directory_listing",
    "thomasnet.com":       "directory_listing",
    "chemicalbook.com":    "directory_listing",
    "chemicalregister.com":"directory_listing",
    "go4worldbusiness.com":"directory_listing",
    "tradeindia.com":      "directory_listing",
    "exportersindia.com":  "directory_listing",
    "globaltradeplaza.com":"directory_listing",
    "ec21.com":            "directory_listing",
    "ecplaza.net":         "directory_listing",
    # Bulk ingredient distributors / resellers
    "bulksupplements.com": "distributor",
    "purebulk.com":        "distributor",
    "laballey.com":        "distributor",
    "bulkapothecary.com":  "distributor",
    "ingredi.com":         "distributor",
    "spectrumchemical.com":"distributor",
    "chemistrywarehouse.com":"distributor",
    "boxnutra.com":        "distributor",
    "bulkfoods.com":       "distributor",
    "ingredientsonline.com":"distributor",
    "ingredientdepot.ca":  "distributor",
    "ingredientdepot.com": "distributor",
    "labdepotinc.com":     "distributor",
    "univarsolutions.com": "distributor",
    "brenntag.com":        "distributor",
    "azelis.com":          "distributor",
    "barentz.com":          "distributor",
    "nutraceuticalsgroup.com":"distributor",
    # Lab / research reagent houses — small quantities, research grade
    "sigmaaldrich.com":    "lab_reagent",
    "fishersci.com":       "lab_reagent",
    "thermofisher.com":    "lab_reagent",
    "vwr.com":             "lab_reagent",
    "tcichemicals.com":    "lab_reagent",
    "oakwoodchemical.com": "lab_reagent",
    "chemexper.com":       "lab_reagent",
    "emdmillipore.com":    "lab_reagent",
    "merckmillipore.com":  "lab_reagent",
    "caymanchem.com":      "lab_reagent",
    # Manufacturer-direct — mid-sized and specialty producers that show up
    # repeatedly in our BOM ingredient set. These are *single-entity* domains
    # (one company, one product line), not aggregators. When this tier matches
    # provenance lifts to 'website_explicit'.
    "jungbunzlauer.com":   "manufacturer_direct",   # citric acid / excipients
    "chem-impex.com":      "manufacturer_direct",
    "chemimpex.com":       "manufacturer_direct",
    "rpicorp.com":         "manufacturer_direct",   # Research Products Intl
    "sinofi.com":          "manufacturer_direct",   # Chinese mfr, mostly APIs
    "vivioninc.com":       "manufacturer_direct",
    "dsm.com":             "manufacturer_direct",
    "basf.com":            "manufacturer_direct",
    "cargill.com":         "manufacturer_direct",
    "adm.com":             "manufacturer_direct",
    "roquette.com":        "manufacturer_direct",
    "ingredion.com":       "manufacturer_direct",
    "kerry.com":            "manufacturer_direct",
    "lonza.com":           "manufacturer_direct",
    "evonik.com":          "manufacturer_direct",
}


# Currency conversion to USD. Update annually; sandbox-grade approximations.
_FX_TO_USD = {
    "USD": 1.0, "$": 1.0,
    "EUR": 1.07, "€": 1.07,
    "GBP": 1.27, "£": 1.27,
    "INR": 0.012, "₹": 0.012, "RS": 0.012, "RUPEE": 0.012, "RUPEES": 0.012,
    "CNY": 0.14, "RMB": 0.14, "¥": 0.14, "YUAN": 0.14,
    "JPY": 0.0067,
    "AUD": 0.66, "CAD": 0.74, "CHF": 1.13, "SGD": 0.74,
}

# Per-unit conversion to per-kg.
_LB_TO_KG = 2.20462  # 1 kg = 2.20462 lb, so $/lb × 2.20462 = $/kg
_G_TO_KG = 1000.0


def _first(d: dict, keys: tuple) -> str | None:
    """Return the first non-empty value among keys (defensive lookup)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _detect_currency(s: str) -> float:
    """Return USD multiplier for first recognised currency token in s. Default USD."""
    up = s.upper()
    # Check explicit currency words first (longer tokens win)
    for token in sorted(_FX_TO_USD.keys(), key=len, reverse=True):
        if token in ("USD", "$"):
            continue
        if token in up:
            return _FX_TO_USD[token]
    return 1.0  # default USD


def _detect_unit_factor(s: str) -> float:
    """Return per-kg multiplier. e.g. $/lb → 2.20462, $/g → 1000, $/kg → 1.0"""
    up = s.upper()
    if re.search(r"/?\s*LB\b|PER\s*LB|/?\s*POUND\b", up):
        return _LB_TO_KG
    if re.search(r"/?\s*G\b|PER\s*GRAM\b|/?\s*GRAM\b", up) and "/KG" not in up and "/ KG" not in up:
        return _G_TO_KG
    return 1.0  # default per-kg


def _parse_suppliers(raw: str, ingredient_name: str) -> list[dict]:
    """Extract JSON array from model output. Tolerates markdown fences + leading prose."""
    if not raw or not raw.strip():
        return []
    # Greedy DOTALL; strip ```json fences if present.
    txt = raw.strip()
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", txt, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return [{"supplier_name": "research_result", "notes": txt[:400]}]


def _parse_price(price_str: str | None) -> float | None:
    """Extract USD/kg float, normalising currency + unit.

    Returns None if no numeric content found. Returns 0.0 if price is suspect
    (e.g. "Request Quote", "Contact for pricing").
    """
    if not price_str:
        return None
    s = str(price_str).strip()
    # Reject pure quote-on-request strings — no number to extract anyway.
    nums = re.findall(r"\d+(?:[.,]\d+)?", s)
    if not nums:
        return None
    # Normalise commas (e.g. "1,200" → "1200") then take the first 1-2 numerics
    values = [float(n.replace(",", "")) for n in nums[:2]]
    midpoint = sum(values) / len(values)
    # Apply currency + unit conversion
    fx = _detect_currency(s)
    unit = _detect_unit_factor(s)
    usd_per_kg = midpoint * fx * unit
    # Sanity: anything above $100,000/kg or below $0.01/kg is almost certainly garbage
    if usd_per_kg > 100_000 or usd_per_kg < 0.01:
        return None
    return round(usd_per_kg, 4)


def _parse_moq(moq_str: str | None) -> float | None:
    """Extract float kg from '25 kg', '1-5 kg', '100kg', '50 lb' (converted)."""
    if not moq_str:
        return None
    s = str(moq_str)
    nums = re.findall(r"\d+(?:[.,]\d+)?", s)
    if not nums:
        return None
    val = float(nums[0].replace(",", ""))
    # Convert lb → kg if quoted in lb
    if re.search(r"\bLB\b|POUND", s.upper()):
        val = val / _LB_TO_KG
    return round(val, 3)


# Matches a percentage the model may emit inside a grade / purity / spec /
# evidence / qualifier string. We ONLY trust an explicit `%` suffix —
# trigger-word heuristics ("grade", "pure", "minimum") produce too many
# false positives because product names in this domain lean on those words
# (e.g. "Pure Biotin Powder", "Vitamin E T-50", "Lab Grade, $94.14"). False
# positives in Purity_Pct are worse than missing values because downstream
# gating treats Purity_Pct as a spec-fit signal.
_PCT_WITH_SIGN = re.compile(
    r"(?:≥|>=|≤|<=|~|=|>|<)?\s*(\d{2,3}(?:\.\d+)?)\s*%"
)

# Words that, when they immediately follow a `NN%` token, indicate the number
# is NOT a purity claim — it's a price premium, discount, margin, commission,
# etc. ("50% premium", "30% cheaper", "10% off", "20% discount").
_PCT_NON_PURITY_CONTEXT = re.compile(
    r"^\s*(?:premium|cheaper|discount|off|higher|lower|more|less|margin|commission|markup|savings?|bigger|smaller)\b",
    re.IGNORECASE,
)


def _parse_purity_pct(*candidates: str | list | None) -> float | None:
    """Extract a numeric purity percentage from one or more text candidates.

    The model emits purity info unpredictably — sometimes under `grade`,
    sometimes under `purity`, sometimes buried in `evidence_snippet`, and
    sometimes comma-tokenised into the `certifications` list (e.g. the
    ``["≥", "9", "8"]`` pathology seen in the enriched DB). This function
    walks candidates in priority order and returns the first plausible
    percentage in the 50–100 range (purities below 50% are almost always
    noise — e.g. "40% of stearic acid content").

    Returns None when no candidate yields a plausible value.
    """
    for cand in candidates:
        if not cand:
            continue
        if isinstance(cand, list):
            text = " ".join(str(c) for c in cand if c)
        else:
            text = str(cand)
        # 1) Explicit "XX%" / "≥XX%" / ">=XX.X%" — strongest signal.
        # Hyphenated ranges ("98-99%") look like a detached first number
        # followed by a second number with a %. Prepend the detached number
        # so the regex can catch both and we pick the conservative (lower)
        # value — a "98-99%" claim is a promise of ≥98%.
        explicit_matches: list[float] = []
        for m in _PCT_WITH_SIGN.finditer(text):
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            if not (50.0 <= val <= 100.0):
                continue
            # Reject if the `%` is followed by a price/margin context word
            # ("50% premium", "30% cheaper", "10% off" …). These are monetary
            # commentary, not purity claims.
            tail = text[m.end(): m.end() + 24]
            if _PCT_NON_PURITY_CONTEXT.match(tail):
                continue
            explicit_matches.append(val)
            # Also pick up a range peer like "98-99%": the leading number
            # in the hyphenated range sits right before the matched span.
            start = m.start()
            peer = re.search(r"(\d{2,3}(?:\.\d+)?)\s*-\s*$", text[:start])
            if peer:
                try:
                    peer_val = float(peer.group(1))
                except ValueError:
                    peer_val = None
                if peer_val is not None and 50.0 <= peer_val <= 100.0:
                    explicit_matches.append(peer_val)
        if explicit_matches:
            return round(min(explicit_matches), 2)
    return None


def _normalize_certs(raw_certs) -> list[str]:
    """Coerce to list[str]. Handles list, comma-string, single string, None."""
    if not raw_certs:
        return []
    if isinstance(raw_certs, list):
        return [str(c).strip() for c in raw_certs if c]
    if isinstance(raw_certs, str):
        # Split on commas / semicolons
        parts = re.split(r"[,;]", raw_certs)
        return [p.strip() for p in parts if p.strip()]
    return [str(raw_certs)]


def _normalize_country(raw_country) -> str | None:
    """Resolve to ISO-3166 display form. Returns None for unknown inputs.

    Wraps enrichment.enrichers.country_iso.normalize_country so callers don't
    have to import the helper directly. Unknown/unresolved countries return
    None; the caller should WARN and persist NULL rather than writing garbage.
    """
    resolved = iso_normalize_country(raw_country)
    if raw_country and not resolved:
        logger.warning(f"  country: unresolved input {raw_country!r} — persisting NULL")
    return resolved


def _hostname(url: str | None) -> str | None:
    """Return the lowercase hostname of a URL, or None if unparseable."""
    if not url:
        return None
    try:
        host = urlparse(str(url)).hostname
    except Exception:
        return None
    return host.lower() if host else None


def _load_blocklist(conn: sqlite3.Connection) -> set[str]:
    """Fetch the full URL_Blocklist once per run. Cheap (< 100 rows)."""
    try:
        return {r[0] for r in conn.execute("SELECT Hostname FROM URL_Blocklist").fetchall()}
    except sqlite3.OperationalError:
        # Table may not exist on older DBs (pre-migrate_provenance). Fail-open.
        return set()


def _hostname_blocked(url: str | None, blocklist: set[str]) -> bool:
    """Match url's host against blocklist, handling bare-domain / www. / subdomains."""
    host = _hostname(url)
    if not host or not blocklist:
        return False
    if host in blocklist:
        return True
    # Also match without a leading 'www.' and against bare-domain form
    stripped = host[4:] if host.startswith("www.") else host
    if stripped in blocklist:
        return True
    # Finally match any parent domain (e.g. host=news.reddit.com, blocked=reddit.com)
    parts = stripped.split(".")
    for i in range(1, len(parts) - 1):
        if ".".join(parts[i:]) in blocklist:
            return True
    return False


def _classify_archetype(url: str | None) -> str:
    """Return one of: directory_listing, distributor, lab_reagent,
    manufacturer_direct, unknown.

    Parent-domain walk: news.made-in-china.com also matches made-in-china.com.
    Unknown hosts default to 'unknown' (not 'manufacturer_direct') — we prefer
    explicit unknowns over optimistic guesses.
    """
    host = _hostname(url)
    if not host:
        return "unknown"
    # Exact + strip www.
    candidates = [host]
    if host.startswith("www."):
        candidates.append(host[4:])
    # Parent-domain walk
    parts = (host[4:] if host.startswith("www.") else host).split(".")
    for i in range(1, len(parts) - 1):
        candidates.append(".".join(parts[i:]))
    for c in candidates:
        if c in _ARCHETYPE_HOSTS:
            return _ARCHETYPE_HOSTS[c]
    return "unknown"


def _classify_provenance(
    url: str | None, country_ok: bool, evidence: str | None, archetype: str = "unknown"
) -> str:
    """Provenance_Confidence tiers — how much trust to place in the row's claims.

    Decision tree (first match wins):
      - no url, no country                 → unknown
      - no url, country only               → model_inferred
      - url + archetype=directory_listing  → directory_listing
      - url + archetype=distributor        → directory_listing (trustworthy but indirect)
      - url + archetype=lab_reagent        → directory_listing (niche market tier)
      - url + archetype=manufacturer_direct→ website_explicit
      - url + archetype=unknown + country  → directory_listing
      - url + archetype=unknown, no country→ model_inferred

    'vendor_verified' is only set by Supplier_Master joins (trade-register
    match). 'website_explicit' requires a known manufacturer-direct host,
    which this function can flag but can't confirm — that's what the
    two-pass verification job is for.
    """
    if not url and not country_ok:
        return "unknown"
    if not url:
        return "model_inferred"
    # url is present
    if archetype == "manufacturer_direct":
        return "website_explicit"
    if archetype in ("directory_listing", "distributor", "lab_reagent"):
        return "directory_listing"
    # archetype == 'unknown'
    return "directory_listing" if country_ok else "model_inferred"


# Corporate suffixes to strip before fuzzy-matching. Keep this short —
# over-aggressive stripping creates false positives ("Pure Labs LLC" vs
# "Impure Labs LLC" shouldn't collapse).
_CORP_SUFFIX_RE = re.compile(
    r"\b(?:inc|incorporated|ltd|limited|llc|llp|co|company|corp|corporation|"
    r"gmbh|ag|sa|srl|spa|pvt|pty|bv|nv|plc|kg|kk)\b\.?",
    re.IGNORECASE,
)


def _normalize_supplier_name(name: str) -> str:
    """Lowercase, strip punctuation + corporate suffixes, collapse whitespace."""
    s = name.lower()
    s = _CORP_SUFFIX_RE.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s)   # punctuation → space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fuzzy_match_supplier(
    name: str, existing: list[tuple[int, str]], threshold: int = 90
) -> tuple[int, str, int] | None:
    """Return (id, matched_name, score) of best fuzzy match above threshold, or None.

    Both input and candidates are normalised (lowercase, strip corporate
    suffixes + punctuation, collapse whitespace) before scoring. Uses
    rapidfuzz.token_sort_ratio — permissive for reordering ("ACME Inc USA"
    ↔ "USA ACME Inc") but correctly conservative for subset-extension
    ("Fisher Scientific" ≠ "Thermo Fisher Scientific"). token_set_ratio
    scores 100 on that subset case and would collapse different companies.
    """
    if not existing:
        return None
    from rapidfuzz import process, fuzz
    norm_name = _normalize_supplier_name(name)
    if not norm_name:
        return None
    norm_existing = [(eid, ename, _normalize_supplier_name(ename)) for eid, ename in existing]
    norm_list = [t[2] for t in norm_existing]
    match = process.extractOne(
        norm_name, norm_list, scorer=fuzz.token_sort_ratio, score_cutoff=threshold
    )
    if not match:
        return None
    _matched, score, idx = match
    eid, ename, _ = norm_existing[idx]
    return eid, ename, int(score)


class SupplierWebEnricher:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)
        self._blocklist_cache: set[str] | None = None
        self._supplier_cache: list[tuple[int, str]] | None = None
        # Fuzzy-match threshold. 90 handles "ACME, Inc." vs "ACME Inc" cleanly
        # without collapsing genuinely different names like "Pure Bulk" vs
        # "Purely Nutrition".
        self._fuzzy_threshold = 90

    def _get_blocklist(self, conn: sqlite3.Connection) -> set[str]:
        if self._blocklist_cache is None:
            self._blocklist_cache = _load_blocklist(conn)
        return self._blocklist_cache

    def _get_supplier_cache(self, conn: sqlite3.Connection) -> list[tuple[int, str]]:
        if self._supplier_cache is None:
            rows = conn.execute("SELECT Id, Name FROM Supplier").fetchall()
            self._supplier_cache = [(r[0], r[1]) for r in rows]
        return self._supplier_cache

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
        """Exact-match first, then fuzzy-match (token_set_ratio >= 90), then insert.

        Fuzzy-match catches the "Made-in-China.com (various suppliers)" class
        of dup where the same entity shows up under slightly different names
        across runs. When a fuzzy match hits, we reuse the existing SupplierId
        and log the collision so the pattern is visible.
        """
        cache = self._get_supplier_cache(conn)
        # Exact match in cache first (case-sensitive, which matches the old
        # behaviour — suppliers often have capitalisation differences that we
        # *do* want to treat as the same entity; those fall through to fuzzy).
        for sid, sname in cache:
            if sname == supplier_name:
                return sid
        # Fuzzy match against existing suppliers.
        match = _fuzzy_match_supplier(supplier_name, cache, threshold=self._fuzzy_threshold)
        if match:
            sid, matched_name, score = match
            logger.info(
                f"  fuzzy-matched {supplier_name!r} to existing {matched_name!r} "
                f"(id={sid}, score={score})"
            )
            return sid
        # Insert new supplier + update cache.
        cur = conn.execute("INSERT OR IGNORE INTO Supplier (Name) VALUES (?)", (supplier_name,))
        sid = cur.lastrowid or conn.execute(
            "SELECT Id FROM Supplier WHERE Name = ?", (supplier_name,)
        ).fetchone()[0]
        cache.append((sid, supplier_name))
        return sid

    def _existing_prices_for_ingredient(self, conn: sqlite3.Connection, canonical_id: int) -> list[float]:
        """Return all non-null Price_USD_Per_KG already on file for this canonical ingredient."""
        rows = conn.execute(
            """SELECT Price_USD_Per_KG FROM Supplier_Commercial
               WHERE CanonicalIngredientId = ? AND Price_USD_Per_KG IS NOT NULL""",
            (canonical_id,)
        ).fetchall()
        return [r[0] for r in rows if r[0] is not None]

    def _is_outlier(self, candidate: float, baseline: list[float]) -> bool:
        """Reject if candidate is >10× max or <0.1× min of existing baseline.
        Requires at least 2 baseline points to even start judging."""
        if not candidate or len(baseline) < 2:
            return False
        sorted_b = sorted(baseline)
        # Use median for stability against existing outliers
        mid = sorted_b[len(sorted_b) // 2]
        if mid <= 0:
            return False
        ratio = candidate / mid
        return ratio > 10.0 or ratio < 0.1

    def _write_commercial(
        self, conn: sqlite3.Connection,
        supplier_id: int, canonical_id: int,
        parsed: dict, source_url: str | None
    ) -> bool:
        """Write a Supplier_Commercial row. Returns True on success, False if rejected."""
        # Defensive field-name lookups (model may free-style key names)
        price_raw = _first(parsed, _PRICE_KEYS)
        moq_raw = _first(parsed, _MOQ_KEYS)
        url = source_url or _first(parsed, _URL_KEYS)
        country = _normalize_country(parsed.get("country"))
        certs = _normalize_certs(_first(parsed, _CERT_KEYS))
        purity_qualifier = ", ".join(certs[:3]) if certs else None
        evidence_raw = _first(parsed, _EVIDENCE_KEYS)
        evidence = (str(evidence_raw).strip()[:_EVIDENCE_MAX_LEN]) if evidence_raw else None

        price = _parse_price(price_raw)
        moq = _parse_moq(moq_raw)
        # Parse numeric Purity_Pct from whichever field the model decided to
        # stash purity info in. Priority: explicit grade/purity/spec field >
        # the cert list we just assembled (captures cases where models
        # comma-tokenised "≥98" into the cert array) > evidence snippet.
        grade_raw = _first(parsed, _GRADE_KEYS)
        purity_pct = _parse_purity_pct(grade_raw, certs, purity_qualifier, evidence)

        # --- Provenance gate 1: URL blocklist.
        # Reject the whole row if the source URL is on a known non-supplier
        # domain list (wikipedia, reddit, linkedin, placeholders, etc.).
        if url:
            blocklist = self._get_blocklist(conn)
            if _hostname_blocked(url, blocklist):
                logger.warning(
                    f"  blocklist reject: canonical_id={canonical_id} "
                    f"supplier_id={supplier_id} url={url!r}"
                )
                return False

        # --- Provenance gate 2: outlier QC against existing prices.
        if price is not None:
            baseline = self._existing_prices_for_ingredient(conn, canonical_id)
            if self._is_outlier(price, baseline):
                logger.warning(
                    f"  QC reject: canonical_id={canonical_id} supplier_id={supplier_id} "
                    f"price=${price}/kg is outlier vs baseline (median≈${sorted(baseline)[len(baseline)//2]:.2f}/kg, n={len(baseline)})"
                )
                return False

        # --- Provenance gate 3: classify archetype + confidence on write.
        archetype = _classify_archetype(url)
        provenance = _classify_provenance(url, country is not None, evidence, archetype)

        conn.execute(
            """INSERT OR REPLACE INTO Supplier_Commercial
               (SupplierId, CanonicalIngredientId, Price_USD_Per_KG, MOQ_KG,
                Country_Origin, Price_Type, Price_Source, Confidence,
                Source_URL, Last_Updated, Grade_Unverified, Purity_Pct,
                Purity_Qualifier, Provenance_Confidence, Evidence_Snippet,
                URL_Archetype)
               VALUES (?, ?, ?, ?, ?, 'web_search', 'google_search', ?, ?, datetime('now'), 1, ?, ?, ?, ?, ?)""",
            (supplier_id, canonical_id, price, moq, country, _CONFIDENCE_WEB, url,
             purity_pct, purity_qualifier, provenance, evidence, archetype)
        )
        return True

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
                url = _first(s, _URL_KEYS)
                if self._write_commercial(conn, supplier_id, canonical_id, s, url):
                    written += 1
            except Exception as e:
                logger.warning(f"  Failed to write supplier {name!r}: {e}")
        if not written:
            logger.warning(
                f"  {ingredient_name}: found {len(suppliers)} rows but 0 written "
                f"(field-name mismatch, price unparseable, or all QC-rejected)"
            )
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
