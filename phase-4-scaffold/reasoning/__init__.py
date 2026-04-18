"""Phase 4 reasoning core.

All tool-facing modules import from `reasoning.base` (Tool, ToolResult,
compound_confidence). Every public entry point returns a ToolResult so the
planner can chain results and propagate evidence/confidence uniformly.
"""
