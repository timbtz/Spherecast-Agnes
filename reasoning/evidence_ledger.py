"""Append-only evidence store.

Every assertion that flows into a gate, a compliance outcome, or a
supplier score must reference one or more EvidenceIds. This module is
the single write point for the Evidence_Ledger table created in
schema/migration_v12.sql.

Append-only is enforced at the API level (no `update`, no `delete`).
We rely on sqlite's autoincrement PK to keep ids stable for citing.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class EvidenceRecord:
    evidence_id: int
    source: str
    url: Optional[str]
    claim: str
    raw_excerpt: Optional[str]
    confidence: Optional[float]
    fetched_at: str


class EvidenceLedger:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def add(
        self,
        source: str,
        claim: str,
        url: Optional[str] = None,
        raw_excerpt: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO Evidence_Ledger (Source, Url, Claim, RawExcerpt, Confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source, url, claim, raw_excerpt, confidence),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_many(self, rows: Iterable[dict]) -> List[int]:
        ids: List[int] = []
        for r in rows:
            ids.append(
                self.add(
                    source=r["source"],
                    claim=r["claim"],
                    url=r.get("url"),
                    raw_excerpt=r.get("raw_excerpt"),
                    confidence=r.get("confidence"),
                )
            )
        return ids

    def get(self, evidence_id: int) -> Optional[EvidenceRecord]:
        row = self.conn.execute(
            "SELECT * FROM Evidence_Ledger WHERE EvidenceId = ?", (evidence_id,)
        ).fetchone()
        if not row:
            return None
        return EvidenceRecord(
            evidence_id=row["EvidenceId"],
            source=row["Source"],
            url=row["Url"],
            claim=row["Claim"],
            raw_excerpt=row["RawExcerpt"],
            confidence=row["Confidence"],
            fetched_at=row["FetchedAt"],
        )

    def get_trail(self, evidence_ids: Iterable[int]) -> List[EvidenceRecord]:
        return [r for r in (self.get(i) for i in evidence_ids) if r is not None]

    def serialize_for_ui(self, evidence_ids: Iterable[int]) -> str:
        """JSON the UI can render directly under each gate row."""
        trail = [
            {
                "id": r.evidence_id,
                "source": r.source,
                "url": r.url,
                "claim": r.claim,
                "confidence": r.confidence,
            }
            for r in self.get_trail(evidence_ids)
        ]
        return json.dumps(trail, indent=2)
