"""Infer the FUNCTIONAL ROLE of an ingredient inside a recipe.

Two ingredients can share a canonical molecule but play different roles
(e.g. citric acid as 'acidulant' vs 'chelator'). The Substitution gate
must compare like-for-like, so we attach role labels to both incumbent
and candidate before deciding compatibility.

Strategy:
  1. Try a tight rule table (functional class + ingredient signal).
  2. Multi-role molecules return a set; downstream picks per recipe slot.
  3. Fall back to 'unknown' with low confidence — never invent a role.
"""

from __future__ import annotations

from typing import Optional, Set

from .base import Tool, ToolResult


# Canonical ingredient name (lowercase) -> primary role in CPG formulations.
# Hand-curated; expand as the BOM grows. Anything not here is 'unknown'.
ROLE_RULES: dict = {
    # Acids / acidulants
    "citric acid": "acidulant",
    "malic acid": "acidulant",
    "lactic acid": "acidulant",
    "phosphoric acid": "acidulant",
    "ascorbic acid": "antioxidant",  # role priority over acidulant in beverages
    "tartaric acid": "acidulant",
    # Sweeteners (caloric)
    "sucrose": "sweetener",
    "glucose": "sweetener",
    "fructose": "sweetener",
    "high fructose corn syrup": "sweetener",
    "honey": "sweetener",
    # Sweeteners (high intensity)
    "sucralose": "high-intensity-sweetener",
    "aspartame": "high-intensity-sweetener",
    "stevia": "high-intensity-sweetener",
    "rebaudioside a": "high-intensity-sweetener",
    "monk fruit extract": "high-intensity-sweetener",
    # Preservatives
    "potassium sorbate": "preservative",
    "sodium benzoate": "preservative",
    "calcium propionate": "preservative",
    # Colors
    "beta carotene": "colorant",
    "annatto": "colorant",
    "caramel color": "colorant",
    "anthocyanin": "colorant",
    # Emulsifiers / stabilizers / thickeners
    "lecithin": "emulsifier",
    "soy lecithin": "emulsifier",
    "sunflower lecithin": "emulsifier",
    "xanthan gum": "thickener",
    "guar gum": "thickener",
    "pectin": "thickener",
    "carrageenan": "stabilizer",
    "gum arabic": "stabilizer",
    # Minerals / actives
    "magnesium oxide": "mineral-fortificant",
    "magnesium citrate": "mineral-fortificant",
    "magnesium stearate": "lubricant",  # primary role in tabletting; see MULTI_ROLE below
    "vegetable magnesium stearate": "lubricant",
    "calcium stearate": "lubricant",
    "stearic acid": "lubricant",
    "zinc gluconate": "mineral-fortificant",
    "calcium carbonate": "mineral-fortificant",
    # Vitamins
    "cyanocobalamin": "vitamin-fortificant",
    "methylcobalamin": "vitamin-fortificant",
    "cholecalciferol": "vitamin-fortificant",
    "alpha-tocopherol": "antioxidant",
    # Functionals / botanicals
    "caffeine": "functional-stimulant",
    "l-theanine": "functional-amino",
    "creatine monohydrate": "functional-performance",
    "whey protein isolate": "protein-source",
    "pea protein isolate": "protein-source",
}


# Molecules that legitimately wear multiple hats — caller must pick by recipe slot.
MULTI_ROLE_MOLECULES: dict = {
    "ascorbic acid": {"antioxidant", "acidulant", "vitamin-fortificant"},
    "citric acid": {"acidulant", "chelator", "preservative-aid"},
    "lecithin": {"emulsifier", "antioxidant"},
    "alpha-tocopherol": {"antioxidant", "vitamin-fortificant"},
    # Magnesium stearate: the playbook §4 worked case. Primary role is
    # lubricant (tabletting), but it also contributes magnesium — this
    # matters because stearic acid can cover the lubricant role but NOT
    # the magnesium source. The role gate uses the multi-role set to
    # detect partial substitutes that need human review.
    "magnesium stearate": {"lubricant", "mineral-fortificant"},
    "vegetable magnesium stearate": {"lubricant", "mineral-fortificant"},
    # Calcium stearate covers lubricant but swaps the mineral (Ca vs Mg).
    "calcium stearate": {"lubricant", "mineral-fortificant"},
}


def _normalize(name: str) -> str:
    return (name or "").strip().lower()


class RoleInferrer(Tool):
    name = "role_inferrer"

    def _run(self, ingredient_name: str, recipe_slot_hint: Optional[str] = None) -> ToolResult:
        key = _normalize(ingredient_name)
        if not key:
            return ToolResult(result=None, confidence=0.0, refusal="empty_ingredient_name")

        # Multi-role: prefer the slot hint if it matches one of the valid roles.
        if key in MULTI_ROLE_MOLECULES:
            roles = MULTI_ROLE_MOLECULES[key]
            if recipe_slot_hint and recipe_slot_hint in roles:
                return ToolResult(result=recipe_slot_hint, confidence=0.85)
            primary = ROLE_RULES.get(key)
            if primary:
                return ToolResult(result=primary, confidence=0.65)
            return ToolResult(result=None, confidence=0.4, refusal="multi_role_no_slot_hint")

        # Single-role rule hit.
        role = ROLE_RULES.get(key)
        if role:
            return ToolResult(result=role, confidence=0.9)

        # Fallback — explicit unknown so downstream gates can drop confidence.
        return ToolResult(result="unknown", confidence=0.2)


def roles_for(name: str) -> Set[str]:
    """Convenience: return the full role set for a molecule (incl. multi-role)."""
    key = _normalize(name)
    if key in MULTI_ROLE_MOLECULES:
        return set(MULTI_ROLE_MOLECULES[key])
    if key in ROLE_RULES:
        return {ROLE_RULES[key]}
    return {"unknown"}


def covers_roles(candidate_name: str, incumbent_name: str) -> Set[str]:
    """Return the set of incumbent roles the candidate does NOT cover.

    Empty set means the candidate is a full role-equivalent of the
    incumbent. Non-empty means it's a partial substitute — the caller
    should fork / defer to human review.

    Example:
        covers_roles('stearic acid', 'magnesium stearate')
            -> {'mineral-fortificant'}        # lubricant match, Mg missing

        covers_roles('vegetable magnesium stearate', 'magnesium stearate')
            -> set()                           # full match
    """
    cand_roles = roles_for(candidate_name)
    inc_roles = roles_for(incumbent_name)
    if "unknown" in inc_roles:
        return set()  # can't fail what we don't know
    return inc_roles - cand_roles


# --------------------------------------------------------------- self-test


def _self_test() -> None:
    """Property-based checks for multi-role ambiguity.

    Run via `python -m reasoning.role_inferrer`. Exits non-zero on the
    first failed assertion so CI / pre-commit can gate on role-table
    regressions.
    """
    # Multi-role molecules must appear in both ROLE_RULES (with a
    # primary role) and MULTI_ROLE_MOLECULES (with the full set).
    for name, roles in MULTI_ROLE_MOLECULES.items():
        assert isinstance(roles, set) and len(roles) >= 2, (
            f"MULTI_ROLE_MOLECULES[{name!r}] must carry >=2 roles; got {roles!r}"
        )
        primary = ROLE_RULES.get(name)
        assert primary in roles, (
            f"ROLE_RULES[{name!r}]={primary!r} is not in the multi-role set {roles!r}"
        )

    # Anchor case: magnesium stearate is multi-role, stearic acid is
    # single-role lubricant, so stearic acid partially covers MgSt.
    gap = covers_roles("stearic acid", "magnesium stearate")
    assert gap == {"mineral-fortificant"}, (
        f"stearic acid should miss the mineral-fortificant role; got {gap!r}"
    )

    # Full coverage path.
    gap_full = covers_roles("vegetable magnesium stearate", "magnesium stearate")
    assert gap_full == set(), (
        f"vegetable MgSt should fully cover MgSt; got missing={gap_full!r}"
    )

    # Wrong-role path: lecithin is an emulsifier, not a lubricant.
    gap_wrong = covers_roles("soy lecithin", "magnesium stearate")
    assert gap_wrong == {"lubricant", "mineral-fortificant"}, (
        f"soy lecithin should miss both MgSt roles; got {gap_wrong!r}"
    )

    # Recipe-slot disambiguation for ascorbic acid.
    tool = RoleInferrer()
    r = tool("ascorbic acid", recipe_slot_hint="acidulant")
    assert r.result == "acidulant" and r.confidence >= 0.8

    r2 = tool("ascorbic acid")
    assert r2.result == "antioxidant"  # primary role from ROLE_RULES

    # Unknown path never invents a role.
    r3 = tool("totally-made-up-ingredient")
    assert r3.result == "unknown" and r3.confidence <= 0.3

    print(f"role_inferrer self-test OK "
          f"({len(ROLE_RULES)} rules, {len(MULTI_ROLE_MOLECULES)} multi-role)")


if __name__ == "__main__":
    _self_test()
