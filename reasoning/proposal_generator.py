"""Phase 4: Generate structured consolidation proposals using Claude API."""
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
MIN_SCORE_THRESHOLD = 0.05
MIN_COMPANY_COUNT = 2
TARGET_PROPOSAL_COUNT = 50

logger = logging.getLogger("agnes.proposal_generator")


class ProposalGenerator:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def run(self) -> None:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set — proposal generation requires this key. Exiting.")
            return
        client = anthropic.Anthropic(api_key=api_key)
        opportunities = self._get_top_opportunities()

        logger.info(f"Generating proposals for {len(opportunities)} opportunities")

        for opp in opportunities:
            context = self._build_context(opp)
            proposal = self._generate_proposal(client, context, opp)
            self._store_proposal(opp["id"], proposal)
            self._extract_and_store_citations(client, opp["id"], proposal)

        logger.info(f"Generated {len(opportunities)} proposals.")
        self._write_markdown_report()

    def _get_top_opportunities(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT co.Id, ic.Name, ic.CAS_Number, ic.Function,
                      co.Company_Count, co.BOM_Count, co.Current_Supplier_Count,
                      co.Consolidation_Score, co.Recommended_SupplierId, s.Name AS SupplierName,
                      ic.Grade_Flag, ic.SMILES
               FROM Consolidation_Opportunity co
               JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
               LEFT JOIN Supplier s ON s.Id = co.Recommended_SupplierId
               WHERE co.Consolidation_Score >= ?
                 AND co.Company_Count >= ?
                 AND (co.Proposal_Text IS NULL OR co.Proposal_Text = '')
               ORDER BY co.Consolidation_Score DESC
               LIMIT ?""",
            (MIN_SCORE_THRESHOLD, MIN_COMPANY_COUNT, TARGET_PROPOSAL_COUNT),
        ).fetchall()
        conn.close()

        return [
            {
                "id": r[0], "ingredient_name": r[1], "cas_number": r[2],
                "function": r[3], "company_count": r[4], "bom_count": r[5],
                "supplier_count": r[6], "score": r[7],
                "recommended_supplier_id": r[8], "recommended_supplier_name": r[9],
                "grade": r[10], "smiles": r[11],
            }
            for r in rows
        ]

    def _build_context(self, opp: dict) -> dict:
        conn = sqlite3.connect(self.db_path)

        # Companies buying this ingredient
        companies = conn.execute(
            """SELECT DISTINCT c.Name
               FROM SKU_To_Canonical stc
               JOIN Product p ON p.Id = stc.ProductId
               JOIN Company c ON c.Id = p.CompanyId
               JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
               WHERE ic.Name = ? COLLATE NOCASE""",
            (opp["ingredient_name"],),
        ).fetchall()

        # Suppliers currently serving this ingredient
        suppliers = conn.execute(
            """SELECT DISTINCT s.Name
               FROM SKU_To_Canonical stc
               JOIN Supplier_Product sp ON sp.ProductId = stc.ProductId
               JOIN Supplier s ON s.Id = sp.SupplierId
               JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
               WHERE ic.Name = ? COLLATE NOCASE""",
            (opp["ingredient_name"],),
        ).fetchall()

        # Commercial data if available
        commercial = conn.execute(
            """SELECT sc.Price_USD_Per_KG, sc.MOQ_KG, sc.Price_Type, sc.Price_Source
               FROM Supplier_Commercial sc
               JOIN Ingredient_Canonical ic ON ic.Id = sc.CanonicalIngredientId
               WHERE ic.Name = ? COLLATE NOCASE
               ORDER BY sc.Price_USD_Per_KG ASC""",
            (opp["ingredient_name"],),
        ).fetchall()

        # Compliance requirements
        compliance = conn.execute(
            """SELECT pc.Certification, pc.Status
               FROM Product_Compliance pc
               JOIN Product p ON p.Id = pc.ProductId
               JOIN BOM b ON b.ProducedProductId = p.Id
               JOIN BOM_Component bc ON bc.BOMId = b.Id
               JOIN SKU_To_Canonical stc ON stc.ProductId = bc.ConsumedProductId
               JOIN Ingredient_Canonical ic ON ic.Id = stc.CanonicalId
               WHERE ic.Name = ? COLLATE NOCASE
                 AND pc.Status IN ('confirmed', 'claimed', 'implied')""",
            (opp["ingredient_name"],),
        ).fetchall()

        conn.close()
        return {
            "companies": [r[0] for r in companies],
            "current_suppliers": [r[0] for r in suppliers],
            "commercial_data": [
                {"price_usd_per_kg": r[0], "moq_kg": r[1],
                 "price_type": r[2], "source": r[3]}
                for r in commercial
            ],
            "compliance_requirements": [
                {"certification": r[0], "status": r[1]} for r in compliance
            ],
            "grade": opp.get("grade", "unknown"),
            "smiles_available": opp.get("smiles") is not None,
        }

    def _generate_proposal(self, client, context: dict, opp: dict) -> dict:
        system_prompt = """You are Agnes, an AI supply chain analyst for CPG supplement companies.
Generate a structured consolidation proposal for a raw material ingredient.
Be precise, evidence-based, and flag any data gaps explicitly.
Never invent CAS numbers, certifications, or pricing data — only use what is provided."""

        user_prompt = f"""Generate a consolidation proposal for: {opp['ingredient_name']}

INGREDIENT DATA:
- CAS Number: {opp.get('cas_number', 'Not confirmed')}
- Function: {opp.get('function', 'Unknown')}
- Grade: {opp.get('grade', 'unknown')}
- Companies purchasing independently: {opp['company_count']} ({', '.join(context['companies'][:10])})
- Current suppliers: {opp['supplier_count']} ({', '.join(context['current_suppliers'][:5])})
- BOMs containing this ingredient: {opp['bom_count']}
- Consolidation score: {opp['score']:.3f}

COMMERCIAL DATA:
{json.dumps(context['commercial_data'], indent=2) if context['commercial_data'] else 'No commercial data available'}

COMPLIANCE REQUIREMENTS:
{json.dumps(context['compliance_requirements'], indent=2) if context['compliance_requirements'] else 'No compliance data available'}

RECOMMENDED SUPPLIER: {opp.get('recommended_supplier_name', 'To be determined')}

Output a JSON object with these fields:
{{
  "ingredient": "canonical name",
  "cas_number": "CAS or null",
  "current_state": "narrative of current fragmented purchasing",
  "consolidation_opportunity": "narrative of what pooling would achieve",
  "recommended_supplier": "name or TBD",
  "estimated_combined_volume_narrative": "estimate based on company count × typical BOM volume",
  "compliance_assessment": "gap analysis vs requirements",
  "confidence_score": 0.0-1.0,
  "data_gaps": ["list of missing data that would strengthen this proposal"],
  "sources": ["list of data sources used"],
  "proposal_narrative": "2-3 paragraph human-readable proposal"
}}"""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()
        # Extract JSON from response (may be wrapped in markdown)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Could not parse LLM proposal JSON — storing as text")
            return {"proposal_narrative": raw, "confidence_score": 0.5, "sources": ["llm"]}

    def _store_proposal(self, opportunity_id: int, proposal: dict) -> None:
        llm_adjustment = max(-0.10, min(0.10, proposal.get("llm_adjustment", 0.0)))
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """UPDATE Consolidation_Opportunity
               SET Proposal_Text = ?, Proposal_JSON = ?,
                   Compliance_Gap = ?, Generated_At = ?,
                   Score_LLM_Adjustment = ?
               WHERE Id = ?""",
            (
                proposal.get("proposal_narrative", ""),
                json.dumps(proposal),
                json.dumps(proposal.get("data_gaps", [])),
                datetime.utcnow().isoformat(),
                llm_adjustment,
                opportunity_id,
            ),
        )
        conn.commit()
        conn.close()

    def _extract_and_store_citations(self, client, opportunity_id: int, proposal: dict) -> None:
        """Post-process: extract claims from proposal narrative and match to DB sources."""
        import anthropic  # noqa: F401 — already imported in run()
        narrative = proposal.get("proposal_narrative", "")
        sources = proposal.get("sources", [])
        if not narrative:
            return

        extraction_prompt = f"""Extract verifiable claims from this procurement proposal and map each claim to a source.

PROPOSAL:
{narrative}

CONTEXT SOURCES AVAILABLE: {sources}

Return a JSON array of citations. Each element:
{{
  "claim_text": "exact short claim from proposal",
  "source_type": "fda_iid|pubchem|dsld|supplier|openfda|compliance",
  "source_id": "row ID or external identifier if known, else null",
  "source_snippet": "brief excerpt or data point that supports this claim",
  "confidence": 0.0-1.0
}}

Return only the JSON array, no other text. Maximum 8 citations."""

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
            raw = response.content[0].text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            citations = json.loads(raw)
            if not isinstance(citations, list):
                return
            conn = sqlite3.connect(self.db_path)
            for cit in citations[:8]:
                conn.execute(
                    """INSERT INTO Claim_Citation
                       (OpportunityId, ClaimText, SourceType, SourceId, SourceSnippet, Confidence)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        opportunity_id,
                        cit.get("claim_text", "")[:500],
                        cit.get("source_type", "unknown"),
                        str(cit.get("source_id")) if cit.get("source_id") else None,
                        cit.get("source_snippet", "")[:500],
                        float(cit.get("confidence", 0.7)),
                    )
                )
            conn.commit()
            conn.close()
            logger.info(f"Stored {len(citations)} citations for opportunity {opportunity_id}")
        except Exception as e:
            logger.warning(f"Citation extraction failed for opportunity {opportunity_id}: {e}")

    def _write_markdown_report(self) -> None:
        conn = sqlite3.connect(self.db_path)
        proposals = conn.execute(
            """SELECT ic.Name, co.Consolidation_Score, co.Company_Count,
                      co.Proposal_Text, co.Proposal_JSON
               FROM Consolidation_Opportunity co
               JOIN Ingredient_Canonical ic ON ic.Id = co.CanonicalIngredientId
               WHERE co.Proposal_Text IS NOT NULL AND co.Proposal_Text != ''
               ORDER BY co.Consolidation_Score DESC"""
        ).fetchall()
        conn.close()

        lines = ["# Agnes Consolidation Proposals\n", f"Generated: {datetime.utcnow().isoformat()}\n"]
        for i, (name, score, cos, text, proposal_json) in enumerate(proposals, 1):
            lines.append(f"\n---\n\n## Proposal {i}: {name}\n")
            lines.append(f"**Consolidation Score:** {score:.3f} | **Companies:** {cos}\n\n")
            lines.append(text or "_No narrative generated._")
            lines.append("\n")

        report_path = ROOT / "proposals.md"
        report_path.write_text("\n".join(lines))
        logger.info(f"Proposals written to {report_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ProposalGenerator().run()
