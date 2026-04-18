"""Magnesium stearate — Playbook §4 worked case.

The playbook's anchor demo: a multivitamin contract manufacturer that
buys magnesium stearate from three suppliers (CN + IN + US), and wants
Agnes to propose a consolidation. The interesting part is that MgSt is
a *multi-role* ingredient — it's both a tabletting lubricant AND a
source of magnesium. That property exposes the role gate's ambiguity
handling, which doesn't fire on cleaner cases like sucralose.

Candidates we surface:
    * vegetable magnesium stearate — same molecule, vegetable-sourced
      (pharma grade, US supplier). Should recommend cleanly.
    * stearic acid                 — partial substitute: lubricant role
      satisfied, magnesium role not. Should human-review / fork.
    * calcium stearate             — substitute from a different cation;
      lubricant role OK, magnesium replaced. Fork by market.
    * soy lecithin                 — wrong role (emulsifier, not lubricant).
      Should refuse on role gate.

The case is wired so each candidate exercises a different path through
the reasoning chain, giving the demo five distinct decision rationales
in three minutes.
"""

from __future__ import annotations

from typing import List

from reasoning.gate_engine import SkuProfile
from reasoning.supplier_scorer import SupplierFeatures

from ..planner import CandidateBundle
from .anchor_case import AnchorFixture


# Incumbent SMILES approximates magnesium distearate (two stearate chains
# chelating Mg2+). For the demo we don't need chemical perfection — the
# gate uses SMILES only for identity matching, and our candidates differ
# by structure rather than by stereo / tautomer detail.
_MG_ST_SMILES = "CCCCCCCCCCCCCCCCCC(=O)[O-].CCCCCCCCCCCCCCCCCC(=O)[O-].[Mg+2]"

_VEG_MG_ST_SMILES = _MG_ST_SMILES  # chemically identical; source differs
_STEARIC_ACID_SMILES = "CCCCCCCCCCCCCCCCCC(=O)O"
_CALCIUM_STEARATE_SMILES = "CCCCCCCCCCCCCCCCCC(=O)[O-].CCCCCCCCCCCCCCCCCC(=O)[O-].[Ca+2]"
_LECITHIN_SMILES = None  # not a well-defined single molecule


def _incumbent() -> SkuProfile:
    return SkuProfile(
        sku_id=3001,
        canonical_id=305,                  # canonical id used in compliance packs
        smiles=_MG_ST_SMILES,
        unii="70097M6I30",                 # magnesium stearate UNII
        role="lubricant",                   # tableting lubricant role
        form="powder",
        processing="micronized",
        grade="pharma",
        psd_bucket="5-50um",
        surface_area_m2g=9.8,
        bulk_density_gml=0.22,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="supplement",
    )


def _vegetable_candidate() -> CandidateBundle:
    profile = SkuProfile(
        sku_id=3101,
        canonical_id=305,                  # same canonical — equivalent source
        smiles=_VEG_MG_ST_SMILES,
        unii="70097M6I30",
        role="lubricant",
        form="powder",
        processing="micronized",
        grade="pharma",
        psd_bucket="5-50um",
        surface_area_m2g=10.1,
        bulk_density_gml=0.22,
        jurisdictions_approved=["US-FDA", "EU", "CA", "JP"],
        use_class="supplement",
    )
    feats = SupplierFeatures(
        supplier_id=8101, supplier_name="Peter Greven Vegetable Mg Stearate",
        quality=0.93, cost=0.58, logistics=0.80, risk=0.20,
        compliance_pass=False, evidence_ids=[],
    )
    return CandidateBundle(
        candidate_profile=profile,
        candidate_name="vegetable magnesium stearate",
        candidate_supplier_id=feats.supplier_id,
        candidate_supplier_name=feats.supplier_name,
        candidate_country="DE",
        incumbent_precedents={"US-FDA": True, "EU": True, "CA": True, "JP": False},
        supplier_features=feats,
        canonical_ingredient_id=305,
    )


def _stearic_acid_candidate() -> CandidateBundle:
    profile = SkuProfile(
        sku_id=3102,
        canonical_id=310,
        smiles=_STEARIC_ACID_SMILES,
        unii="4ELV7Z65AP",
        role="lubricant",                   # lubricant, yes
        form="powder", processing="micronized",
        grade="pharma",
        psd_bucket="5-50um",
        surface_area_m2g=5.2, bulk_density_gml=0.29,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="supplement",
    )
    feats = SupplierFeatures(
        supplier_id=8102, supplier_name="Croda Stearic Acid (US)",
        quality=0.88, cost=0.68, logistics=0.85, risk=0.20,
        compliance_pass=False, evidence_ids=[],
    )
    return CandidateBundle(
        candidate_profile=profile,
        candidate_name="stearic acid",
        candidate_supplier_id=feats.supplier_id,
        candidate_supplier_name=feats.supplier_name,
        candidate_country="US",
        # Incumbent uses stearic acid in US and EU supplements — precedent yes.
        incumbent_precedents={"US-FDA": True, "EU": True},
        supplier_features=feats,
        canonical_ingredient_id=310,
    )


def _calcium_stearate_candidate() -> CandidateBundle:
    profile = SkuProfile(
        sku_id=3103,
        canonical_id=311,
        smiles=_CALCIUM_STEARATE_SMILES,
        unii="776XM7047L",
        role="lubricant",
        form="powder", processing="micronized",
        grade="pharma",
        psd_bucket="5-50um",
        surface_area_m2g=8.7, bulk_density_gml=0.24,
        # Calcium stearate is approved in US + EU but less common in JP;
        # mark both so the regulatory gate passes in US (the primary J).
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="supplement",
    )
    feats = SupplierFeatures(
        supplier_id=8103, supplier_name="FACI Calcium Stearate (IT)",
        quality=0.86, cost=0.63, logistics=0.72, risk=0.22,
        compliance_pass=False, evidence_ids=[],
    )
    return CandidateBundle(
        candidate_profile=profile,
        candidate_name="calcium stearate",
        candidate_supplier_id=feats.supplier_id,
        candidate_supplier_name=feats.supplier_name,
        candidate_country="IT",
        incumbent_precedents={"US-FDA": True, "EU": True},
        supplier_features=feats,
        canonical_ingredient_id=311,
    )


def _lecithin_candidate() -> CandidateBundle:
    profile = SkuProfile(
        sku_id=3104,
        canonical_id=312,
        smiles=_LECITHIN_SMILES,
        unii="1DI56QDM62",                 # soy lecithin UNII
        role="emulsifier",                  # WRONG ROLE — should refuse
        form="powder", processing=None,
        grade="food",
        psd_bucket=None, surface_area_m2g=None, bulk_density_gml=None,
        jurisdictions_approved=["US-FDA", "EU"],
        use_class="supplement",
    )
    feats = SupplierFeatures(
        supplier_id=8104, supplier_name="ADM Soy Lecithin (US)",
        quality=0.81, cost=0.55, logistics=0.88, risk=0.18,
        compliance_pass=False, evidence_ids=[],
    )
    return CandidateBundle(
        candidate_profile=profile,
        candidate_name="soy lecithin",
        candidate_supplier_id=feats.supplier_id,
        candidate_supplier_name=feats.supplier_name,
        candidate_country="US",
        incumbent_precedents={"US-FDA": True, "EU": True},
        supplier_features=feats,
        canonical_ingredient_id=312,
    )


def build_magnesium_stearate_case(*, include_jp: bool = True) -> AnchorFixture:
    jurisdictions = ["US-FDA", "EU", "CA", "JP"] if include_jp else ["US-FDA", "EU"]
    return AnchorFixture(
        opportunity_id=6305,                # mirrors the canonical id + 6000 prefix
        incumbent_profile=_incumbent(),
        incumbent_name="magnesium stearate",
        use_class="supplement",
        jurisdictions=jurisdictions,
        candidates=[
            _vegetable_candidate(),
            _stearic_acid_candidate(),
            _calcium_stearate_candidate(),
            _lecithin_candidate(),
        ],
    )
