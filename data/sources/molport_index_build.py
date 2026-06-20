"""Build `db_molport_index.sqlite` from Molport's public SMILES dump.

Input
-----
A folder containing the 12 gzipped SMILES files downloaded from Molport's
public "All Stock Compounds" distribution:

    SMILES/iis_smiles-000-000-000--000-499-999.txt.gz
    SMILES/iis_smiles-000-500-000--000-999-999.txt.gz
    ...
    SMILES/iis_smiles-005-500-000--005-999-999.txt.gz

Each file is a TSV with a header row: `SMILES\tSMILES_CANONICAL\tMOLPORTID`.

Output
------
    db_molport_index.sqlite

Schema:
    compounds(
        molport_id      TEXT PRIMARY KEY,
        smiles          TEXT,
        smiles_canonical TEXT
    ) WITHOUT ROWID;
    CREATE INDEX idx_smiles           ON compounds(smiles);
    CREATE INDEX idx_smiles_canonical ON compounds(smiles_canonical);

Size: ~6M rows → ~500–700 MB SQLite file (do NOT commit).

Usage
-----
    python -m enrichment.sources.molport_index_build \
        --src "/path/to/All Stock Compounds/SMILES" \
        --out db_molport_index.sqlite

Runtime: ~3–6 minutes on a modern laptop. Idempotent — re-running drops and
rebuilds the table from scratch.
"""
from __future__ import annotations

import argparse
import gzip
import logging
import sqlite3
import sys
import time
from pathlib import Path

logger = logging.getLogger("agnes.molport.index_build")

BATCH_SIZE = 20_000


def _iter_rows(smiles_file: Path):
    """Yield (molport_id, smiles, smiles_canonical) tuples from one .txt.gz file."""
    with gzip.open(smiles_file, "rt", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()  # skip "SMILES\tSMILES_CANONICAL\tMOLPORTID\n"
        if "MOLPORTID" not in header.upper():
            logger.warning("Unexpected header in %s: %r", smiles_file.name, header.strip())
        for line_no, line in enumerate(fh, 2):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            smiles, smiles_canonical, molport_id = parts
            if not molport_id:
                continue
            yield (molport_id.strip(), smiles.strip(), smiles_canonical.strip())


def build(src_dir: Path, out_path: Path) -> dict:
    """Build the index. Returns stats dict."""
    smiles_files = sorted(src_dir.glob("iis_smiles-*.txt.gz"))
    if not smiles_files:
        raise FileNotFoundError(
            f"No iis_smiles-*.txt.gz files found in {src_dir}. "
            "Expected Molport's SMILES dump folder."
        )

    logger.info("Building %s from %d source files", out_path, len(smiles_files))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(out_path)
    try:
        # Bulk-load pragmas. Safe because we drop/recreate the DB each run.
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -200000")  # 200MB cache
        conn.execute(
            """
            CREATE TABLE compounds (
                molport_id       TEXT PRIMARY KEY,
                smiles           TEXT,
                smiles_canonical TEXT
            ) WITHOUT ROWID
            """
        )

        total = 0
        t0 = time.time()
        for file_idx, smiles_file in enumerate(smiles_files, 1):
            t_file = time.time()
            batch: list[tuple[str, str, str]] = []
            file_count = 0
            for row in _iter_rows(smiles_file):
                batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(
                        "INSERT OR IGNORE INTO compounds (molport_id, smiles, smiles_canonical) VALUES (?, ?, ?)",
                        batch,
                    )
                    file_count += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO compounds (molport_id, smiles, smiles_canonical) VALUES (?, ?, ?)",
                    batch,
                )
                file_count += len(batch)
            total += file_count
            conn.commit()
            logger.info(
                "  [%2d/%d] %-50s +%d rows  (%.1fs)",
                file_idx, len(smiles_files), smiles_file.name, file_count, time.time() - t_file,
            )

        logger.info("Creating indexes on smiles and smiles_canonical...")
        t_idx = time.time()
        conn.execute("CREATE INDEX idx_smiles ON compounds(smiles)")
        conn.execute("CREATE INDEX idx_smiles_canonical ON compounds(smiles_canonical)")
        conn.commit()
        logger.info("Indexes built in %.1fs", time.time() - t_idx)

        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA synchronous = NORMAL")

        row = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()
        logger.info("Total rows: %d", row[0])
        logger.info("Total time: %.1fs", time.time() - t0)

        size_mb = out_path.stat().st_size / (1024 * 1024)
        logger.info("Output size: %.1f MB → %s", size_mb, out_path)

        return {
            "source_files": len(smiles_files),
            "rows": row[0],
            "size_mb": round(size_mb, 1),
            "elapsed_s": round(time.time() - t0, 1),
        }
    finally:
        conn.close()


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build Molport identity index from the public SMILES dump")
    parser.add_argument("--src", required=True, help="Path to the SMILES/ folder (containing iis_smiles-*.txt.gz)")
    parser.add_argument("--out", default="db_molport_index.sqlite", help="Output SQLite path")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    stats = build(Path(args.src), Path(args.out))
    print(stats)


if __name__ == "__main__":
    _cli()
