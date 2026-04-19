"""Idempotent migration: Claim_Citation + Refusal_Log tables + 4 demo trap seeds."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "db_enriched.sqlite"


def migrate(db_path: Path = DB) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS Claim_Citation (
            Id              INTEGER PRIMARY KEY AUTOINCREMENT,
            OpportunityId   INTEGER NOT NULL,
            ClaimText       TEXT NOT NULL,
            SourceType      TEXT NOT NULL,
            SourceId        TEXT,
            SourceUrl       TEXT,
            SourceSnippet   TEXT,
            Confidence      REAL,
            CreatedAt       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (OpportunityId) REFERENCES Consolidation_Opportunity(Id)
        );

        CREATE TABLE IF NOT EXISTS Refusal_Log (
            Id              INTEGER PRIMARY KEY AUTOINCREMENT,
            CanonicalId     INTEGER,
            IngredientName  TEXT NOT NULL,
            Decision        TEXT NOT NULL,
            Justification   TEXT,
            Confidence      REAL,
            BlockingFactors TEXT,
            UnblockHint     TEXT,
            RunId           TEXT,
            CreatedAt       TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_claim_citation_opp ON Claim_Citation(OpportunityId);
        CREATE INDEX IF NOT EXISTS idx_refusal_canonical ON Refusal_Log(CanonicalId);
    """)

    # Relax legacy NOT NULL on Refusal_Log.CanonicalId so coverage-gap refusals
    # (where the ingredient isn't in Ingredient_Canonical at all) can be
    # recorded by no_data_explainer / no_opportunity_explainer. Earlier schema
    # made this NOT NULL, which silently dropped rows via INSERT OR IGNORE.
    # This block is idempotent — it only rebuilds if the old constraint is
    # still present.
    refusal_cols = conn.execute("PRAGMA table_info(Refusal_Log)").fetchall()
    canonical_col = next((c for c in refusal_cols if c[1] == "CanonicalId"), None)
    if canonical_col is not None and canonical_col[3] == 1:  # notnull flag
        conn.executescript("""
            BEGIN;
            CREATE TABLE Refusal_Log_new (
                Id              INTEGER PRIMARY KEY AUTOINCREMENT,
                CanonicalId     INTEGER,
                IngredientName  TEXT NOT NULL,
                Decision        TEXT NOT NULL,
                Justification   TEXT,
                Confidence      REAL,
                BlockingFactors TEXT,
                UnblockHint     TEXT,
                RunId           TEXT,
                CreatedAt       TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO Refusal_Log_new
              (Id, CanonicalId, IngredientName, Decision, Justification,
               Confidence, BlockingFactors, UnblockHint, RunId, CreatedAt)
              SELECT Id, CanonicalId, IngredientName, Decision, Justification,
                     Confidence, BlockingFactors, UnblockHint, RunId, CreatedAt
              FROM Refusal_Log;
            DROP TABLE Refusal_Log;
            ALTER TABLE Refusal_Log_new RENAME TO Refusal_Log;
            CREATE INDEX IF NOT EXISTS idx_refusal_canonical ON Refusal_Log(CanonicalId);
            COMMIT;
        """)
        print("Relaxed Refusal_Log.CanonicalId NOT NULL constraint")

    existing = conn.execute("SELECT COUNT(*) FROM Refusal_Log").fetchone()[0]
    if existing == 0:
        traps = [
            ("Magnesium Stearate", "refuse",
             "Bovine-source Magnesium Stearate conflicts with Vegan certification on 3 affected products (Ultima Replenisher product line). Supplier's animal-derived origin cannot satisfy vegan constraint.",
             0.91, '["vegan_constraint_violation"]',
             "Source plant-derived Magnesium Stearate (e.g. palm-free vegetable grade). Verify supplier origin documentation before substitution."),
            ("Vitamin E", "refuse",
             "Proposed supplier offers 95% purity Vitamin E. BOM specifies ≥99% USP grade. Grade downshift cannot be accepted without reformulation review by quality team.",
             0.87, '["grade_mismatch","purity_below_spec"]',
             "Source USP-verified Vitamin E at ≥99% purity. Obtain certificate of analysis confirming USP compliance before resubmitting."),
            ("Titanium Dioxide", "defer_human_review",
             "Ingredient approved under US FDA IID (oral route). EU REACH restriction RE-2022/63 flags nano-form Titanium Dioxide in food-grade applications. Companies with EU market exposure require jurisdiction-specific review.",
             0.72, '["jurisdiction_divergence","eu_reach_flag"]',
             "Obtain EU-compliant non-nano grade with particle size certification. Human review required to confirm EU market exposure for affected product lines."),
            ("Ascorbic Acid", "defer_human_review",
             "Primary recommended supplier last updated 247 days ago (exceeds 180-day staleness threshold). Pricing confidence downgraded to 0.45. Proposal narrative should not rely on stale price as a savings estimate.",
             0.45, '["stale_supplier_data"]',
             "Re-run price_monitor pipeline to refresh supplier pricing. Confidence will restore to 0.65+ after successful web price fetch."),
        ]

        name_to_id: dict[str, int] = {}
        for (ing_name, *_rest) in traps:
            row = conn.execute(
                "SELECT Id FROM Ingredient_Canonical WHERE Name LIKE ? LIMIT 1",
                (f"%{ing_name.split()[0]}%",)
            ).fetchone()
            if row:
                name_to_id[ing_name] = row[0]

        for (ing_name, decision, justification, confidence, blocking, unblock) in traps:
            resolved_id = name_to_id.get(ing_name, 1)
            conn.execute(
                """INSERT INTO Refusal_Log
                   (CanonicalId, IngredientName, Decision, Justification, Confidence,
                    BlockingFactors, UnblockHint, RunId)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (resolved_id, ing_name, decision, justification, confidence, blocking, unblock, None)
            )
        conn.commit()
        print(f"Seeded {len(traps)} demo trap refusals")

    conn.commit()
    conn.close()
    print("Migration complete: Claim_Citation + Refusal_Log")


if __name__ == "__main__":
    migrate()
