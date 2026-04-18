"""Supplier scout package.

Discovers candidate suppliers we don't already have in the BOM. Plugs
into Tim's enrichment runner via `scout.scout.run_scout()` and writes to
Scout_Candidate (created in migration_v12.sql).
"""
