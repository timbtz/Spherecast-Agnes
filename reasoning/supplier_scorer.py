"""Supplier scoring engine — normalizes price/lead_time/quality and applies user weights."""
import sqlite3
import logging
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).parent.parent
ENRICHED_DB = ROOT / "db_enriched.sqlite"
logger = logging.getLogger("agnes.supplier_scorer")

_DEFAULT_WEIGHTS = {"weight_price": 3.0, "weight_lead_time": 3.0, "weight_quality": 3.0}


def _safe_mean(vals: list[float]) -> float:
    return mean(vals) if vals else 0.5


class SupplierScorer:
    def __init__(self, db_path: str | Path = ENRICHED_DB):
        self.db_path = str(db_path)

    def get_weights(self) -> dict[str, float]:
        """Load weights from Scoring_Config; return defaults if table empty."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT Key, Value FROM Scoring_Config").fetchall()
            conn.close()
            cfg = {r[0]: r[1] for r in rows}
            return {k: cfg.get(k, v) for k, v in _DEFAULT_WEIGHTS.items()}
        except Exception:
            return dict(_DEFAULT_WEIGHTS)

    def save_weights(self, price: float, lead_time: float, quality: float) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        for key, val in [("weight_price", price), ("weight_lead_time", lead_time), ("weight_quality", quality)]:
            conn.execute("INSERT OR REPLACE INTO Scoring_Config (Key, Value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()

    def score_suppliers(self, canonical_ingredient_id: int) -> list[dict]:
        """Return suppliers for this ingredient, ranked by weighted score."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT sc.SupplierId, s.Name as supplier_name,
                      sc.Price_USD_Per_KG, sc.Lead_Time_Days, sc.MOQ_KG,
                      sc.Purity_Pct, sc.Grade_Unverified, sc.Confidence,
                      sc.Country_Origin, sc.Country_Shipping,
                      sc.Price_Source, sc.Price_Type,
                      sc.Purity_Qualifier, sc.Last_Updated,
                      sc.Provenance_Confidence, sc.Corroboration_Score,
                      sc.URL_Archetype, sc.URL_Health,
                      COALESCE(sm.Vetted, 0) as vetted
               FROM Supplier_Commercial sc
               JOIN Supplier s ON s.Id = sc.SupplierId
               LEFT JOIN Supplier_Master sm ON sm.SupplierId = sc.SupplierId
               WHERE sc.CanonicalIngredientId = ?""",
            (canonical_ingredient_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return []

        weights = self.get_weights()
        W_P = weights["weight_price"]
        W_L = weights["weight_lead_time"]
        W_Q = weights["weight_quality"]
        W_total = W_P + W_L + W_Q

        prices = [r["Price_USD_Per_KG"] for r in rows if r["Price_USD_Per_KG"] is not None]
        lead_times = [r["Lead_Time_Days"] for r in rows if r["Lead_Time_Days"] is not None]
        min_p, max_p = (min(prices), max(prices)) if prices else (0, 1)
        min_l, max_l = (min(lead_times), max(lead_times)) if lead_times else (0, 1)

        def _norm(val, lo, hi) -> float:
            if lo == hi:
                return 0.5
            return (val - lo) / (hi - lo)

        results = []
        for r in rows:
            d = dict(r)

            p_score = (1.0 - _norm(r["Price_USD_Per_KG"], min_p, max_p)) if r["Price_USD_Per_KG"] is not None else 0.5
            l_score = (1.0 - _norm(r["Lead_Time_Days"], min_l, max_l)) if r["Lead_Time_Days"] is not None else 0.5

            q_parts = []
            if r["Purity_Pct"] is not None:
                q_parts.append(min(r["Purity_Pct"] / 100.0, 1.0))
            q_parts.append(0.0 if r["Grade_Unverified"] else 1.0)
            if r["Confidence"] is not None:
                q_parts.append(float(r["Confidence"]))
            q_score = _safe_mean(q_parts)

            weighted = (W_P * p_score + W_L * l_score + W_Q * q_score) / W_total

            d["price_score"] = round(p_score, 4)
            d["lead_time_score"] = round(l_score, 4)
            d["quality_score"] = round(q_score, 4)
            d["weighted_score"] = round(weighted, 4)
            results.append(d)

        results.sort(key=lambda x: x["weighted_score"], reverse=True)
        return results

    def score_suppliers_with_context(self, canonical_ingredient_id: int) -> dict:
        """Like score_suppliers() but also returns grade guidelines for UI context."""
        suppliers = self.score_suppliers(canonical_ingredient_id)
        try:
            from reasoning.supplier_guidelines import get_guidelines
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT Grade_Flag FROM Ingredient_Canonical WHERE Id = ?", (canonical_ingredient_id,)
            ).fetchone()
            conn.close()
            guidelines = get_guidelines(row[0] if row else None)
        except Exception:
            guidelines = ""
        return {"suppliers": suppliers, "guidelines": guidelines}
