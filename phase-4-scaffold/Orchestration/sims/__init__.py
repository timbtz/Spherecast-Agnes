"""Demo sims — anchor case + stress injectors.

The anchor case walks one real-looking opportunity end-to-end using
fixture data (no network). It produces the artifacts we show on stage:
a printed verdict + persisted rows in every Phase 4 table.

The stress injector mutates a fixture to force specific failure modes
(gate fail, baseline fail, ambiguous precedent, low confidence) so we
can prove the refusal engine actually refuses.
"""
