"""Phase 4 real-data demo.

Wires Agnes's six-gate / dual-rule / supplier-score / RFQ chain against
Tim's enriched dataset (db_enriched.sqlite). Picks the top-N
Consolidation_Opportunity rows by Consolidation_Score, materializes
SkuProfile + SupplierFeatures from the real tables, calls
plan_opportunity per opp, and writes a consolidated markdown report.

Run via run_real_demo.sh, which first copies the three patched files
(gate_engine.py, compliance_reasoner.py, qualify_candidate.py) into
Tim's repo, runs db_migrate_v12 to materialize the Phase-4 tables, and
runs SubstitutionGraphBuilder to convert Ingredient_Substitution_Rule
rows into Ingredient_Substitution edges.

Read-only against Tim's enrichment tables; writes only to the Phase-4
ledger tables (Substitution_Gate_Result, Compliance_Outcome_4State,
Supplier_Score, Refusal_Record, Drafted_RFQ).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Tim's repo layout — run from repo root.
from Orchestration.planner import CandidateBundle, OpportunityVerdict, plan_opportunity
from reasoning.gate_engine import SkuProfile
from reasoning.supplier_scorer import SupplierFeatures


TOP_N_OPPS = 5
DEFAULT_JURISDICTIONS = ["US-FDA", "EU"]
DEFAULT_USE_CLASS = "supplement"


# ---------------------------------------------------------------- loaders


def fetch_top_opportunities(conn: sqlite3.Connection, n: int) -> List[sqlite3.Row]:
    """Top-N opportunities by Consolidation_Score, only those whose
    incumbent canonical also has at least one substitution edge (otherwise
    there's nothing to gate)."""
    return conn.execute(
        """
        SELECT o.Id                       AS opp_id,
               o.CanonicalIngredientId    AS inc_canonical_id,
               o.Consolidation_Score      AS score,
               o.Company_Count            AS company_count,
               o.BOM_Count                AS bom_count,
               o.Current_Supplier_Count   AS supplier_count,
               o.Recommended_SupplierId   AS recommended_supplier_id,
               c.Name                     AS inc_name,
               c.SMILES                   AS inc_smiles,
               c.UNII_Code                AS inc_unii,
               c.Function                 AS inc_function,
               c.Grade_Flag               AS inc_grade_flag
        FROM Consolidation_Opportunity o
        JOIN Ingredient_Canonical c ON c.Id = o.CanonicalIngredientId
        WHERE EXISTS (
            SELECT 1 FROM Ingredient_Substitution s
            WHERE s.IngredientAId = o.CanonicalIngredientId
               OR s.IngredientBId = o.CanonicalIngredientId
        )
        ORDER BY o.Consolidation_Score DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()


def fetch_candidate_edges(
    conn: sqlite3.Connection, incumbent_canonical_id: int
) -> List[sqlite3.Row]:
    """All canonicals reachable from the incumbent via Ingredient_Substitution
    edges, symmetric (A->B or B->A). We keep whichever side is the candidate."""
    return conn.execute(
        """
        SELECT candidate.Id               AS cand_canonical_id,
               candidate.Name             AS cand_name,
               candidate.SMILES           AS cand_smiles,
               candidate.UNII_Code        AS cand_unii,
               candidate.Function         AS cand_function,
               candidate.Grade_Flag       AS cand_grade_flag,
               s.SubstitutionType         AS sub_type,
               s.Score                    AS edge_score
        FROM Ingredient_Substitution s
        JOIN Ingredient_Canonical candidate ON candidate.Id = CASE
            WHEN s.IngredientAId = :inc THEN s.IngredientBId
            WHEN s.IngredientBId = :inc THEN s.IngredientAId
        END
        WHERE (s.IngredientAId = :inc OR s.IngredientBId = :inc)
          AND s.SubstitutionType != 'incompatible'
        """,
        {"inc": incumbent_canonical_id},
    ).fetchall()


def fetch_suppliers_for_canonical(
    conn: sqlite3.Connection, canonical_id: int
) -> List[sqlite3.Row]:
    """Try the enriched commercial table first; if empty (Tim's enrichment
    pipeline hasn't filled it yet), fall back to Supplier_Product joined
    via SKU_To_Canonical and synthesize neutral commercial stubs so the
    scorer has something to rank. The stubbed path is what the hackathon
    demo actually runs against — Tim's price/lead-time enrichment will
    light up the rich path automatically once Supplier_Commercial has rows."""
    rows = conn.execute(
        """
        SELECT sc.SupplierId           AS supplier_id,
               sup.Name                AS supplier_name,
               sc.Price_USD_Per_KG     AS price_usd_per_kg,
               sc.MOQ_KG               AS moq_kg,
               sc.Lead_Time_Days       AS lead_time_days,
               sc.Country_Origin       AS country_origin,
               sc.Confidence           AS confidence,
               sc.Purity_Pct           AS purity_pct,
               sc.Grade_Unverified     AS grade_unverified
        FROM Supplier_Commercial sc
        JOIN Supplier sup ON sup.Id = sc.SupplierId
        WHERE sc.CanonicalIngredientId = ?
        """,
        (canonical_id,),
    ).fetchall()
    if rows:
        return rows

    # Fallback: synthesize rows from Supplier_Product -> SKU_To_Canonical.
    # Country is guessed from supplier name for a handful of obvious cases.
    class _StubRow(dict):
        def __getitem__(self, k):  # mimic sqlite3.Row's __getitem__
            return super().__getitem__(k)

    fallback = conn.execute(
        """
        SELECT DISTINCT sp.SupplierId AS supplier_id,
               sup.Name              AS supplier_name
        FROM Supplier_Product sp
        JOIN Supplier sup ON sup.Id = sp.SupplierId
        JOIN SKU_To_Canonical m ON m.ProductId = sp.ProductId
        WHERE m.CanonicalId = ?
        """,
        (canonical_id,),
    ).fetchall()

    def _guess_country(name: str) -> Optional[str]:
        n = (name or "").lower()
        if any(t in n for t in ("usa", " us ", "u.s.", "american", "colorcon",
                                "prinova", "ashland", "actus", "capsuline")):
            return "US"
        if any(t in n for t in ("germany", " gmbh", "bayer", "basf")):
            return "DE"
        if any(t in n for t in ("china", "shandong", "shanghai", "hebei", "zhejiang")):
            return "CN"
        if "india" in n or "pvt" in n:
            return "IN"
        return None

    return [_StubRow(
        supplier_id=r[0],
        supplier_name=r[1],
        price_usd_per_kg=None,
        moq_kg=None,
        lead_time_days=None,
        country_origin=_guess_country(r[1]),
        confidence=0.6,         # neutral: we have the supplier but no price
        purity_pct=None,
        grade_unverified=1,
    ) for r in fallback]


def pick_product_id_for_canonical(
    conn: sqlite3.Connection, canonical_id: int
) -> Optional[int]:
    """Return *some* Product.Id mapped to this canonical (we use it as the
    SkuProfile.sku_id so Substitution_Gate_Result FKs resolve cleanly if
    FKs are enforced). Prefers the highest-confidence mapping."""
    row = conn.execute(
        """
        SELECT ProductId
        FROM SKU_To_Canonical
        WHERE CanonicalId = ?
        ORDER BY Confidence DESC
        LIMIT 1
        """,
        (canonical_id,),
    ).fetchone()
    return int(row[0]) if row else None


def fetch_incumbent_precedents(
    conn: sqlite3.Connection, canonical_id: int, jurisdictions: List[str]
) -> Dict[str, bool]:
    """Approximate "do trusted incumbents use this in each jurisdiction?"
    from Product_Compliance rows attached to any product that maps to this
    canonical. If there's at least one 'confirmed' cert in the
    jurisdiction's regime, mark True; otherwise False.

    Mapping of cert -> jurisdiction:
        NSF / USP / InformedSport / BSCG / NonGMO / Kosher / GlutenFree / Vegan / Organic
          -> all count toward US-FDA precedent (US market)
        USP specifically also counts toward US-USP
        We have no EU-only badges in the enriched data, so EU precedent is
        mirrored from any confirmed cert (treating a global cert as
        evidence the incumbent sells the ingredient into EU channels).
    """
    rows = conn.execute(
        """
        SELECT pc.Certification, pc.Status
        FROM Product_Compliance pc
        JOIN SKU_To_Canonical m ON m.ProductId = pc.ProductId
        WHERE m.CanonicalId = ?
        """,
        (canonical_id,),
    ).fetchall()

    confirmed = [r for r in rows if (r[1] or "").lower() == "confirmed"]
    usp_confirmed = any((r[0] or "").upper() == "USP" for r in confirmed)
    any_confirmed = bool(confirmed)

    precedents: Dict[str, bool] = {}
    for j in jurisdictions:
        if j == "US-FDA":
            precedents[j] = any_confirmed
        elif j == "US-USP":
            precedents[j] = usp_confirmed
        elif j == "EU":
            precedents[j] = any_confirmed
        else:
            precedents[j] = False
    return precedents


# ------------------------------------------------------------ feature calc


# Countries we consider low-risk for the purposes of the R component.
LOW_RISK_COUNTRIES = {"US", "USA", "United States",
                      "DE", "Germany", "FR", "France", "NL", "Netherlands",
                      "GB", "UK", "United Kingdom", "CA", "Canada",
                      "JP", "Japan", "CH", "Switzerland", "IE", "Ireland",
                      "DK", "Denmark", "SE", "Sweden", "NO", "Norway",
                      "AT", "Austria", "BE", "Belgium", "IT", "Italy"}


def _infer_form(name: str, function: Optional[str]) -> str:
    """Guess physical form from name / function. Most supplement ingredients
    are powders; a handful are crystalline or granular."""
    n = (name or "").lower()
    if "liquid" in n or "solution" in n or "syrup" in n:
        return "liquid"
    if "flake" in n:
        return "flake"
    if "crystal" in n:
        return "crystal"
    return "powder"


def _infer_grade(grade_flag: Optional[str], function: Optional[str]) -> str:
    """Grade_Flag ∈ {'unknown', 'food', 'pharma', ...}. Default unknown
    unless explicitly marked. Role downshift: excipient:* implies pharma."""
    if grade_flag and grade_flag.lower() not in {"unknown", ""}:
        return grade_flag.lower()
    if function and function.lower().startswith("excipient"):
        return "pharma"
    return "food"  # reasonable default for dietary-supplement ingredients


def _role_from_function(function: Optional[str]) -> Optional[str]:
    """Ingredient_Canonical.Function is formatted like 'excipient:lubricant'
    or 'nutrient:mineral'. We return the portion after the colon so the
    role gate compares 'lubricant' to 'lubricant' rather than
    'excipient:lubricant' to 'excipient:disintegrant'."""
    if not function:
        return None
    if ":" in function:
        return function.split(":", 1)[1].strip().lower() or None
    return function.strip().lower() or None


def _jurisdictions_from_country(country: Optional[str]) -> List[str]:
    if not country:
        return ["US-FDA"]
    c = country.strip()
    approved: List[str] = []
    if c in LOW_RISK_COUNTRIES:
        approved.append("US-FDA")
        approved.append("EU")
    else:
        approved.append("US-FDA")
    return approved


def build_sku_profile(
    *,
    sku_id: int,
    canonical_id: int,
    name: str,
    smiles: Optional[str],
    unii: Optional[str],
    function: Optional[str],
    grade_flag: Optional[str],
    jurisdictions_approved: List[str],
    use_class: str,
) -> SkuProfile:
    return SkuProfile(
        sku_id=sku_id,
        canonical_id=canonical_id,
        smiles=(smiles or None),
        unii=(unii or None),
        role=_role_from_function(function),
        form=_infer_form(name, function),
        processing=None,
        grade=_infer_grade(grade_flag, function),
        psd_bucket=None,
        surface_area_m2g=None,
        bulk_density_gml=None,
        jurisdictions_approved=list(jurisdictions_approved),
        use_class=use_class,
    )


def _normalize_price(price: Optional[float], all_prices: List[float]) -> float:
    """Turn absolute USD/KG into a 0..1 "cheaper is higher" score, relative
    to the other suppliers for this canonical. Missing price -> 0.5 neutral."""
    if price is None or price <= 0:
        return 0.5
    finite = [p for p in all_prices if p and p > 0]
    if not finite:
        return 0.5
    lo, hi = min(finite), max(finite)
    if hi == lo:
        return 0.8   # only one priced supplier -- treat as fine
    # Linear invert: lo -> 0.9, hi -> 0.1.
    return 0.1 + 0.8 * (hi - price) / (hi - lo)


def _lead_time_score(lead_days: Optional[int]) -> float:
    if lead_days is None or lead_days < 0:
        return 0.5
    if lead_days <= 14:
        return 0.9
    if lead_days <= 30:
        return 0.75
    if lead_days <= 60:
        return 0.55
    if lead_days <= 90:
        return 0.4
    return 0.25


def _quality_score(confidence: Optional[float], purity_pct: Optional[float],
                   grade_unverified: Optional[int]) -> float:
    conf = float(confidence or 0.5)
    # Purity -> 0..1. 95..100% maps to 0.8..1.0, below 90% drops sharply.
    if purity_pct is None:
        pur = 0.6
    else:
        p = float(purity_pct)
        if p >= 99.5:
            pur = 1.0
        elif p >= 98:
            pur = 0.9
        elif p >= 95:
            pur = 0.8
        elif p >= 90:
            pur = 0.65
        else:
            pur = 0.45
    # Grade-verified penalty: unverified (1) knocks quality down a bit.
    gv_penalty = 0.1 if (grade_unverified or 1) else 0.0
    return max(0.0, min(1.0, 0.5 * conf + 0.5 * pur - gv_penalty))


def _risk_score(country: Optional[str]) -> float:
    if not country:
        return 0.6
    return 0.15 if country.strip() in LOW_RISK_COUNTRIES else 0.55


def build_supplier_features(sup_row: sqlite3.Row, all_prices: List[float]) -> SupplierFeatures:
    return SupplierFeatures(
        supplier_id=int(sup_row["supplier_id"]),
        supplier_name=str(sup_row["supplier_name"]),
        quality=_quality_score(sup_row["confidence"], sup_row["purity_pct"],
                               sup_row["grade_unverified"]),
        cost=_normalize_price(sup_row["price_usd_per_kg"], all_prices),
        logistics=_lead_time_score(sup_row["lead_time_days"]),
        risk=_risk_score(sup_row["country_origin"]),
        compliance_pass=False,  # planner flips this to True after qualify
        evidence_ids=[],
    )


# ------------------------------------------------------------ main loop


def run_one_opportunity(
    conn: sqlite3.Connection, opp: sqlite3.Row,
    jurisdictions: List[str], use_class: str,
) -> OpportunityVerdict:
    inc_canonical_id = int(opp["inc_canonical_id"])
    inc_sku_id = pick_product_id_for_canonical(conn, inc_canonical_id) or inc_canonical_id

    incumbent_profile = build_sku_profile(
        sku_id=inc_sku_id,
        canonical_id=inc_canonical_id,
        name=str(opp["inc_name"]),
        smiles=opp["inc_smiles"],
        unii=opp["inc_unii"],
        function=opp["inc_function"],
        grade_flag=opp["inc_grade_flag"],
        jurisdictions_approved=list(jurisdictions),
        use_class=use_class,
    )

    inc_precedents = fetch_incumbent_precedents(conn, inc_canonical_id, jurisdictions)

    bundles: List[CandidateBundle] = []
    for edge in fetch_candidate_edges(conn, inc_canonical_id):
        cand_canonical_id = int(edge["cand_canonical_id"])
        suppliers = fetch_suppliers_for_canonical(conn, cand_canonical_id)
        if not suppliers:
            continue
        all_prices = [s["price_usd_per_kg"] for s in suppliers]
        cand_sku_id = pick_product_id_for_canonical(conn, cand_canonical_id) or cand_canonical_id

        for sup in suppliers:
            cand_profile = build_sku_profile(
                sku_id=cand_sku_id,
                canonical_id=cand_canonical_id,
                name=str(edge["cand_name"]),
                smiles=edge["cand_smiles"],
                unii=edge["cand_unii"],
                function=edge["cand_function"],
                grade_flag=edge["cand_grade_flag"],
                jurisdictions_approved=_jurisdictions_from_country(sup["country_origin"]),
                use_class=use_class,
            )
            feats = build_supplier_features(sup, all_prices)
            bundles.append(CandidateBundle(
                candidate_profile=cand_profile,
                candidate_name=str(edge["cand_name"]),
                candidate_supplier_id=int(sup["supplier_id"]),
                candidate_supplier_name=str(sup["supplier_name"]),
                candidate_country=sup["country_origin"],
                incumbent_precedents=dict(inc_precedents),
                supplier_features=feats,
                canonical_ingredient_id=cand_canonical_id,
            ))

    verdict = plan_opportunity(
        conn=conn,
        opportunity_id=int(opp["opp_id"]),
        incumbent_profile=incumbent_profile,
        incumbent_name=str(opp["inc_name"]),
        use_class=use_class,
        jurisdictions=list(jurisdictions),
        candidates=bundles,
    )
    return verdict


# ---------------------------------------------------------------- report


def render_report(verdicts: List[OpportunityVerdict], opps: List[sqlite3.Row]) -> str:
    lines: List[str] = []
    lines.append("# Agnes — Phase 4 Real-Data Demo")
    lines.append("")
    lines.append(
        f"Ran the full six-gate / dual-rule / supplier-score / RFQ chain "
        f"against Tim's enriched dataset. Evaluated the top "
        f"{len(verdicts)} consolidation opportunities."
    )
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append("| Opp | Incumbent | Candidates | Recommend+Review | Refused | Top supplier | Score | RFQs |")
    lines.append("|----:|:----------|-----------:|-----------------:|--------:|:-------------|------:|-----:|")
    for opp, v in zip(opps, verdicts):
        n_candidates = len(v.qualifications)
        n_pass = sum(1 for q in v.qualifications if q.decision in ("recommend", "defer_human_review"))
        n_ref = sum(1 for q in v.qualifications if q.decision.startswith("refuse"))
        top = v.ranked_suppliers[0] if v.ranked_suppliers else None
        top_name = top["supplier_name"] if top else "—"
        top_score = f"{top['score']:.3f}" if top else "—"
        lines.append(
            f"| {int(opp['opp_id'])} | {opp['inc_name']} | {n_candidates} | "
            f"{n_pass} | {n_ref} | {top_name} | {top_score} | {len(v.drafted_rfq_ids)} |"
        )
    lines.append("")

    for opp, v in zip(opps, verdicts):
        lines.append(f"## Opportunity #{int(opp['opp_id'])} — {opp['inc_name']}")
        lines.append("")
        lines.append(
            f"- consolidation_score: `{opp['score']:.3f}` · "
            f"companies: {opp['company_count']} · BOMs: {opp['bom_count']} · "
            f"current suppliers: {opp['supplier_count']}"
        )
        lines.append(f"- candidates evaluated: {len(v.qualifications)}")
        decisions: Dict[str, int] = {}
        for q in v.qualifications:
            decisions[q.decision] = decisions.get(q.decision, 0) + 1
        lines.append(f"- decision breakdown: {decisions}")
        if v.ranked_suppliers:
            lines.append("- top-5 ranked suppliers:")
            for r in v.ranked_suppliers[:5]:
                lines.append(
                    f"  - **{r['supplier_name']}** (id {r['supplier_id']}) — "
                    f"score `{r['score']:.3f}` · "
                    f"Q={r['components']['Q']:.2f} "
                    f"C={r['components']['C']:.2f} "
                    f"L={r['components']['L']:.2f} "
                    f"R={r['components']['R']:.2f}"
                )
        if v.drafted_rfq_ids:
            lines.append(f"- drafted RFQs: {v.drafted_rfq_ids}")
        lines.append("")
        lines.append(v.summary_md)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- entry


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Agnes Phase-4 real-data demo")
    p.add_argument("--db", default=os.environ.get("AGNES_DB", "db_enriched.sqlite"),
                   help="Path to Tim's enriched sqlite DB")
    p.add_argument("--out", default="demo_real.md",
                   help="Markdown report output path")
    p.add_argument("--top-n", type=int, default=TOP_N_OPPS,
                   help="How many opportunities to evaluate")
    p.add_argument("--use-class", default=DEFAULT_USE_CLASS)
    p.add_argument("--jurisdictions", nargs="+", default=DEFAULT_JURISDICTIONS)
    args = p.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        pass

    try:
        opps = fetch_top_opportunities(conn, args.top_n)
        if not opps:
            print("ERROR: no opportunities with substitution edges found. "
                  "Did you run SubstitutionGraphBuilder first?", file=sys.stderr)
            return 3

        verdicts: List[OpportunityVerdict] = []
        for opp in opps:
            print(f"[demo_real] evaluating opportunity {opp['opp_id']} — {opp['inc_name']}")
            try:
                v = run_one_opportunity(conn, opp, args.jurisdictions, args.use_class)
                verdicts.append(v)
            except Exception as exc:  # noqa: BLE001 — we want a per-opp isolate
                print(f"  ! failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                # Emit an empty verdict placeholder so the report still renders.
                verdicts.append(OpportunityVerdict(
                    opportunity_id=int(opp["opp_id"]),
                    incumbent_name=str(opp["inc_name"]),
                    use_class=args.use_class,
                    jurisdictions=list(args.jurisdictions),
                    summary_md=f"### FAILED — {type(exc).__name__}: {exc}",
                ))

        report = render_report(verdicts, opps)
        Path(args.out).write_text(report)
        print(f"[demo_real] wrote {args.out}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
