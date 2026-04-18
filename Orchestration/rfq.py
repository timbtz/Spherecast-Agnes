"""RFQ (Request for Quotation) builder.

Given a shortlist of qualified candidates, build structured RFQ rows in
the RFQ table. We *never* auto-send — the Status stays 'draft' until a
human confirms. The UI (Eng3's surface) presents the drafted RFQ and
a "Send" button that flips Status to 'sent' with a timestamp.

The spec JSON is the contract we hand to suppliers — it locks:
    * canonical identity (SMILES + UNII when available)
    * required role
    * required form / grade / PSD
    * target jurisdictions
    * quantity band
    * required certifications
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RfqSpec:
    canonical_name: str
    smiles: Optional[str]
    unii: Optional[str]
    required_role: str
    required_form: Optional[str]
    required_grade: Optional[str]
    required_psd_bucket: Optional[str]
    target_markets: List[str]
    quantity_band_kg: str                          # e.g. "500-2000"
    required_certifications: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "canonical_name": self.canonical_name,
                "smiles": self.smiles,
                "unii": self.unii,
                "required_role": self.required_role,
                "required_form": self.required_form,
                "required_grade": self.required_grade,
                "required_psd_bucket": self.required_psd_bucket,
                "target_markets": self.target_markets,
                "quantity_band_kg": self.quantity_band_kg,
                "required_certifications": self.required_certifications,
                "notes": self.notes,
            },
            indent=2,
            sort_keys=True,
        )


def draft_rfq(
    conn: sqlite3.Connection,
    opportunity_id: int,
    candidate_supplier_name: str,
    canonical_ingredient_id: int,
    spec: RfqSpec,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO RFQ
          (OpportunityId, CandidateSupplierName, CanonicalIngredientId,
           SpecJson, TargetMarkets, QuantityBandKg, Status)
        VALUES (?, ?, ?, ?, ?, ?, 'draft')
        """,
        (
            opportunity_id,
            candidate_supplier_name,
            canonical_ingredient_id,
            spec.to_json(),
            json.dumps(spec.target_markets),
            spec.quantity_band_kg,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def mark_sent(conn: sqlite3.Connection, rfq_id: int) -> None:
    """Human-confirmed send — sets Status='sent' and stamps SentAt."""
    conn.execute(
        "UPDATE RFQ SET Status='sent', SentAt=CURRENT_TIMESTAMP WHERE RfqId = ? AND Status='draft'",
        (rfq_id,),
    )
    conn.commit()


def record_response(conn: sqlite3.Connection, rfq_id: int, response_json: str) -> None:
    conn.execute(
        "UPDATE RFQ SET Status='response_received', ResponseJson = ? WHERE RfqId = ?",
        (response_json, rfq_id),
    )
    conn.commit()


def list_draft_rfqs(conn: sqlite3.Connection, opportunity_id: int) -> List[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM RFQ WHERE OpportunityId = ? AND Status='draft'",
        (opportunity_id,),
    ).fetchall()
    return [dict(r) for r in rows]
