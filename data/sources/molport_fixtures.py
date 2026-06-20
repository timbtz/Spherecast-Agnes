"""Reference supplier envelopes for the four anchor ingredients, shaped to match the Molport v3 API response format.

Activated via `MOLPORT_FIXTURES_ONLY=1` when the live Molport scraper is not configured.
Molport IDs are resolved against `db_molport_index.sqlite` (6M-compound SMILES index from
Molport's public dump) and are verifiable compound pages. Soy lecithin (8002-43-5) is a
phospholipid mixture with no single Molport entry; its ID is a placeholder.

Prices are retail/lab-scale figures from public vendor listings. Every row carries
`price_type='retail_proxy'` and `grade_unverified=1` after passing through
`flatten_suppliers`, so the compliance and scoring layers treat them as unverified.
Keys are lowercased CAS strings.
"""
from __future__ import annotations

FIXTURES_BY_CAS: dict[str, dict] = {
    # Magnesium stearate — ubiquitous flow agent
    "557-04-0": {
        "Molecule": {
            "Molport Id": "Molport-006-111-835",  # verified against 6M-row Molport index
            "IUPAC": "magnesium stearate",
            "CAS": "557-04-0",
            "Suppliers": [
                {
                    "Supplier Name": "Sigma-Aldrich",
                    "Origin Country ISO": "US",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": ">=95%",
                        "Catalog Id": "M6-111-835-SA-01",
                        "Packings": [
                            {"Amount": 100, "Measure": "g", "Price": 42.50, "Currency": "USD", "Delivery Days": 3, "Stock": "In Stock"},
                            {"Amount": 500, "Measure": "g", "Price": 148.00, "Currency": "USD", "Delivery Days": 3, "Stock": "In Stock"},
                            {"Amount": 1, "Measure": "kg", "Price": 265.00, "Currency": "USD", "Delivery Days": 5, "Stock": "Backorder"},
                        ],
                    }],
                },
                {
                    "Supplier Name": "TCI Chemicals",
                    "Origin Country ISO": "JP",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": ">98%",
                        "Catalog Id": "M6-111-835-TCI-01",
                        "Packings": [
                            {"Amount": 500, "Measure": "g", "Price": 165.00, "Currency": "USD", "Delivery Days": 7, "Stock": "In Stock"},
                        ],
                    }],
                },
            ],
        },
        "_scrape_meta": {"source": "fixture", "scraper_version": "fixture-0.1"},
    },

    # Stearic acid — often substituted for magnesium stearate
    "57-11-4": {
        "Molecule": {
            "Molport Id": "Molport-002-317-291",  # verified against 6M-row Molport index
            "IUPAC": "stearic acid",
            "CAS": "57-11-4",
            "Suppliers": [
                {
                    "Supplier Name": "Sigma-Aldrich",
                    "Origin Country ISO": "US",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": ">=98.5%",
                        "Catalog Id": "M2-317-291-SA-01",
                        "Packings": [
                            {"Amount": 250, "Measure": "g", "Price": 28.00, "Currency": "USD", "Delivery Days": 3, "Stock": "In Stock"},
                            {"Amount": 1, "Measure": "kg", "Price": 85.00, "Currency": "USD", "Delivery Days": 3, "Stock": "In Stock"},
                        ],
                    }],
                },
                {
                    "Supplier Name": "Alfa Aesar",
                    "Origin Country ISO": "US",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": ">97%",
                        "Catalog Id": "M2-317-291-AA-01",
                        "Packings": [
                            {"Amount": 500, "Measure": "g", "Price": 55.00, "Currency": "USD", "Delivery Days": 5, "Stock": "In Stock"},
                        ],
                    }],
                },
            ],
        },
        "_scrape_meta": {"source": "fixture", "scraper_version": "fixture-0.1"},
    },

    # Soy lecithin — common emulsifier; allergen-flagged.
    # NB: soy lecithin is a mixture (phosphatidylcholine + phosphatidylethanolamine
    # + phosphatidylinositol + ...), not a single compound — so Molport does not
    # sell it as one catalogue entry. The ID below is a placeholder; the scraper
    # path will return [] for this CAS, and fixtures is the only source of supplier
    # rows for lecithin in the demo.
    "8002-43-5": {
        "Molecule": {
            "Molport Id": "Molport-007-901-114",  # placeholder — lecithin is a mixture, not a single compound
            "IUPAC": "soy lecithin",
            "CAS": "8002-43-5",
            "Suppliers": [
                {
                    "Supplier Name": "Sigma-Aldrich",
                    "Origin Country ISO": "US",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": "food-grade",
                        "Catalog Id": "M7-901-114-SA-01",
                        "Packings": [
                            {"Amount": 500, "Measure": "g", "Price": 78.00, "Currency": "USD", "Delivery Days": 5, "Stock": "In Stock"},
                            {"Amount": 1, "Measure": "kg", "Price": 132.00, "Currency": "USD", "Delivery Days": 5, "Stock": "In Stock"},
                        ],
                    }],
                },
            ],
        },
        "_scrape_meta": {"source": "fixture", "scraper_version": "fixture-0.1"},
    },

    # Ascorbic acid (vitamin C) — included to have a non-excipient anchor
    "50-81-7": {
        "Molecule": {
            "Molport Id": "Molport-001-792-501",  # verified against 6M-row Molport index
            "IUPAC": "ascorbic acid",
            "CAS": "50-81-7",
            "Suppliers": [
                {
                    "Supplier Name": "DSM",
                    "Origin Country ISO": "NL",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": "USP",
                        "Catalog Id": "M1-792-501-DSM-01",
                        "Packings": [
                            {"Amount": 1, "Measure": "kg", "Price": 18.50, "Currency": "USD", "Delivery Days": 10, "Stock": "In Stock"},
                        ],
                    }],
                },
                {
                    "Supplier Name": "CSPC",
                    "Origin Country ISO": "CN",
                    "Shipping Country ISO": "US",
                    "Catalogue": [{
                        "Purity": "USP/EP",
                        "Catalog Id": "M1-792-501-CSPC-01",
                        "Packings": [
                            {"Amount": 1, "Measure": "kg", "Price": 12.80, "Currency": "USD", "Delivery Days": 21, "Stock": "In Stock"},
                        ],
                    }],
                },
            ],
        },
        "_scrape_meta": {"source": "fixture", "scraper_version": "fixture-0.1"},
    },
}


def lookup_fixture(cas: str) -> dict | None:
    """Return a pre-baked Molport-shaped envelope for a known demo CAS."""
    if not cas:
        return None
    return FIXTURES_BY_CAS.get(cas.strip().lower())
