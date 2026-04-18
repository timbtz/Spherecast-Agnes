"""Download `db_molport_index.sqlite` from a GitHub Release (or any HTTPS URL).

Why this exists
---------------
The Molport identity index is ~1.65 GB (5.97M compounds) — too large to live
in the git repo itself. We publish it as a GitHub Release asset (or any
static file host) and fetch it on demand. With the index in place, the
scraper can:

1. Refuse to scrape SMILES that aren't in Molport's catalogue
   (anti-hallucination pre-flight).
2. Skip the search page and navigate directly to the canonical compound
   URL, because we have the Molport ID → real URL mapping.
3. Validate that the page it actually landed on matches the ID it asked
   for — catches any selector drift that would otherwise leak fake data
   into the supplier table.

Without the index, the scraper still works (falls back to search-page
parsing + the fixture table for anchor demo CASes), but it can no longer
rule out Molport-ID hallucination.

Usage
-----
    # Use the default URL (set REPO + VERSION below, or override with --url)
    python scripts/download_index.py

    # Explicit URL and destination
    python scripts/download_index.py \\
        --url https://github.com/ORG/REPO/releases/download/vX.Y/db_molport_index.sqlite \\
        --out db_molport_index.sqlite

The file will be written atomically (downloaded to `<out>.part` then renamed
on success) so interrupted downloads never leave a corrupt DB in place.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

# Update these to match the repo + release tag where the index lives.
DEFAULT_REPO = "timbtz/Spherecast-Agnes"
DEFAULT_TAG = "molport-index-v1"
DEFAULT_ASSET = "db_molport_index.sqlite"
DEFAULT_URL = (
    f"https://github.com/{DEFAULT_REPO}/releases/download/{DEFAULT_TAG}/{DEFAULT_ASSET}"
)

# Sanity bounds — the real file is ~1.65 GB; reject anything obviously wrong.
MIN_BYTES = 500 * 1024 * 1024        # 500 MB
MAX_BYTES = 3 * 1024 * 1024 * 1024   # 3 GB


def _format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _progress(done: int, total: int, started: float) -> str:
    pct = (done / total * 100) if total else 0.0
    elapsed = time.time() - started
    rate = done / elapsed if elapsed > 0 else 0
    eta = (total - done) / rate if rate > 0 else 0
    return (
        f"\r  {_format_bytes(done):>10} / {_format_bytes(total):<10} "
        f"({pct:5.1f}%)  {_format_bytes(int(rate))}/s  "
        f"ETA {int(eta // 60):02d}:{int(eta % 60):02d}"
    )


def download(url: str, out_path: Path, expected_sha256: str | None = None) -> dict:
    """Stream `url` to `out_path`, atomically. Returns stats dict on success."""
    part = out_path.with_suffix(out_path.suffix + ".part")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    req = Request(url, headers={"User-Agent": "agnes-download-index/0.1"})
    print(f"Downloading from: {url}")
    started = time.time()
    sha = hashlib.sha256()
    total = 0
    with urlopen(req, timeout=60) as resp:
        size_hdr = resp.headers.get("Content-Length")
        total_expected = int(size_hdr) if size_hdr else 0
        if total_expected and total_expected < MIN_BYTES:
            raise RuntimeError(
                f"Server reports {total_expected} bytes — too small for a Molport index "
                f"(expected >= {MIN_BYTES}). Wrong URL?"
            )
        if total_expected > MAX_BYTES:
            raise RuntimeError(
                f"Server reports {total_expected} bytes — larger than sanity cap "
                f"({MAX_BYTES}). Refusing."
            )
        with open(part, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                sha.update(chunk)
                total += len(chunk)
                if total_expected:
                    sys.stdout.write(_progress(total, total_expected, started))
                    sys.stdout.flush()
    sys.stdout.write("\n")

    digest = sha.hexdigest()
    if expected_sha256 and digest != expected_sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA-256 mismatch — expected {expected_sha256}, got {digest}. "
            "File was deleted; re-run to retry."
        )
    shutil.move(str(part), str(out_path))

    elapsed = time.time() - started
    return {
        "bytes": total,
        "elapsed_s": round(elapsed, 1),
        "sha256": digest,
        "path": str(out_path),
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch db_molport_index.sqlite from a GitHub Release asset"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MOLPORT_INDEX_URL", DEFAULT_URL),
        help=f"URL of the index file (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--out",
        default="db_molport_index.sqlite",
        help="Where to write the file (default: ./db_molport_index.sqlite)",
    )
    parser.add_argument(
        "--sha256",
        default=os.environ.get("MOLPORT_INDEX_SHA256"),
        help="Optional SHA-256 to verify after download",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if output file already exists",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    if out_path.exists() and not args.force:
        size = out_path.stat().st_size
        print(
            f"Already present: {out_path} ({_format_bytes(size)}). "
            "Re-run with --force to overwrite."
        )
        return

    try:
        stats = download(args.url, out_path, expected_sha256=args.sha256)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nDone in {stats['elapsed_s']}s — {_format_bytes(stats['bytes'])}")
    print(f"  path: {stats['path']}")
    print(f"  sha256: {stats['sha256']}")
    print(
        "\nThe Molport scraper and smoke tests will now auto-detect this file. "
        "No further setup required."
    )


if __name__ == "__main__":
    _cli()
