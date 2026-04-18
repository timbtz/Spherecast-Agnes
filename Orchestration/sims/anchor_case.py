"""Anchor case fixture.

Scenario: a US-based functional beverage company runs an opportunity to
consolidate two SKUs of high-intensity sweetener (incumbent: sucralose
from supplier A in CN, candidate alternates: sucralose from supplier B
in US; stevia from supplier C in MY). Target markets: US-FDA + EU.

This fixture is intentionally well-formed so the happy path runs all
the way through to drafted RFQs. Stress injectors break individual
fields to demonstrate refusal behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from reasoning.gate_engine import SkuProfile
from reasoning.supplier_scorer import SupplierFeatures

from ..planner import CandidateBundle


@dataclass
class AnchorFixture:
    opportunity_id: int
    incumbent_profile: SkuProfile
    incumbent_name: str
    use_class: str
    jurisdictions: List[str]
    candidates: List[CandidateBundle]


def build_anchor_case() -> AnchorFixture:
    incumbent = SkuProfile(
        sku_id=1001,
        canonical_id=42,
        smiles="ClC[C@H]1O[C@H](O[C@@H]2[C@@H](O)[C@H](O)[C@@H](CO)O[C@H]2Cl)[C@H](O)[C@@H](O)[C@@H]1Cl",
        unii="96K6UQ3ZD4",
        role="high-intensity-sweetener",
        form="powder",
        processing="micronized",
        grade="food",
        psd_bucket="50-200um",
        surface_area_m2g=1.4,
        bulk_density_gml=0.55,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )

    # Candidate 1: same molecule, different supplier (US, pharma grade).
    cand1_profile = SkuProfile(
        sku_id=2001,
        canonical_id=42,
        smiles=incumbent.smiles,
        unii=incumbent.unii,
        role="high-intensity-sweetener",
        form="powder",
        processing="micronized",
        grade="pharma",
        psd_bucket="50-200um",
        surface_area_m2g=1.5,
        bulk_density_gml=0.56,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )
    cand1_supplier = SupplierFeatures(
        supplier_id=9001,
        supplier_name="Tate & Lyle (Splenda)",
        quality=0.92,
        cost=0.55,         # cleaner US-side cost (no ocean freight)
        logistics=0.85,
        risk=0.20,
        compliance_pass=True,
        evidence_ids=[],
    )

    # Candidate 2: cross-molecule (stevia rebA), supplier in MY.
    cand2_profile = SkuProfile(
        sku_id=2002,
        canonical_id=58,
        smiles="O=C(O[C@@H]1O[C@H](CO)[C@@H](O)[C@H](O)[C@H]1O)[C@]23CC[C@@H]4[C@@](C)(CC[C@H]5C(=C)CC[C@@]45C)C2(C3)C",
        unii="2Z37WT5RBQ",
        role="high-intensity-sweetener",
        form="powder",
        processing="spray-dried",
        grade="food",
        psd_bucket="50-200um",
        surface_area_m2g=2.1,
        bulk_density_gml=0.42,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="beverage",
    )
    cand2_supplier = SupplierFeatures(
        supplier_id=9002,
        supplier_name="PureCircle",
        quality=0.88,
        cost=0.62,
        logistics=0.65,
        risk=0.30,
        compliance_pass=True,
        evidence_ids=[],
    )

    return AnchorFixture(
        opportunity_id=7777,
        incumbent_profile=incumbent,
        incumbent_name="sucralose",
        use_class="beverage",
        jurisdictions=["US-FDA", "EU"],
        candidates=[
            CandidateBundle(
                candidate_profile=cand1_profile,
                candidate_name="sucralose",
                candidate_supplier_id=cand1_supplier.supplier_id,
                candidate_supplier_name=cand1_supplier.supplier_name,
                candidate_country="US",
                incumbent_precedents={"US-FDA": True, "EU": True},
                supplier_features=cand1_supplier,
                canonical_ingredient_id=42,
            ),
            CandidateBundle(
                candidate_profile=cand2_profile,
                candidate_name="stevia",
                candidate_supplier_id=cand2_supplier.supplier_id,
                candidate_supplier_name=cand2_supplier.supplier_name,
                candidate_country="MY",
                incumbent_precedents={"US-FDA": True, "EU": True},
                supplier_features=cand2_supplier,
                canonical_ingredient_id=58,
            ),
        ],
    )
