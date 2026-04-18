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
