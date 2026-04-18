# Molport index upload — READ THIS FIRST

This folder contains **only** the Molport identity-index additions —
a focused, minimal drop for a single commit on the Clean-4 branch.

**Do NOT upload this file itself** (`UPLOAD-INSTRUCTIONS.md`). It's for you.

## What's in here

```
Molport-index-upload/
├── UPLOAD-INSTRUCTIONS.md                    ← do NOT upload (this file)
├── .gitignore                                ← upload (REPLACES existing)
├── enrichment/
│   └── sources/                              ← upload entire folder
│       ├── __init__.py
│       ├── README.md                          (updated — adds index docs)
│       ├── molport.py                         (3-path + new fields: currency, stock_status, is_minimum_order)
│       ├── molport_cache.py
│       ├── molport_fixtures.py                (real Molport IDs + Stock + Catalog Id baked in)
│       ├── molport_index.py                   (NEW — 6M-row identity index wrapper)
│       ├── molport_index_build.py             (NEW — one-time builder CLI)
│       ├── molport_scraper.py                 (index-aware + pack_stock selector)
│       └── smoke_test_molport.py              (extended — 49 assertions)
└── scripts/
    └── download_index.py                      (NEW — fetches DB from Release asset)
```

Total: **11 files**, ~80 KB.

## Step 1 — Make hidden files visible + clean caches

1. macOS Finder hides dotfiles. Press **⌘ + ⇧ + .** in Finder while you're
   looking at `Molport-index-upload/` to reveal `.gitignore`.
2. Delete `enrichment/sources/__pycache__/` if it appears — it's a Python
   cache folder left over from the smoke test run. Select in Finder → ⌘+Delete.
   (GitHub's upload preview will also let you uncheck it if it slips in.)

## Step 2 — Open the Clean-4 branch

https://github.com/timbtz/Spherecast-Agnes/tree/Clean-4

Confirm the branch selector in the top-left says **Clean-4** (not
`master`, not `phase-4`).

## Step 3 — Upload

1. Click the green **`Add file`** button → **Upload files**.
2. In Finder, open `~/Documents/Molport-index-upload/`.
3. Select everything **except `UPLOAD-INSTRUCTIONS.md`**:
   - `.gitignore`
   - `enrichment/` (folder)
   - `scripts/` (folder)
4. Drag the selection onto the GitHub upload area. GitHub preserves the
   folder structure, so `enrichment/sources/molport_index.py` lands
   in the right place automatically.
5. GitHub will tell you the 5 existing files are being replaced
   (`.gitignore`, `enrichment/sources/README.md`, `molport.py`,
   `molport_fixtures.py`, `molport_scraper.py`, `smoke_test_molport.py`)
   and 3 new ones are being added (`molport_index.py`,
   `molport_index_build.py`, `scripts/download_index.py`). That's correct.
6. Scroll down. Commit message:

   ```
   feat: Molport identity index + richer supplier rows

   - Adds enrichment/sources/molport_index.py (6M-row SQLite wrapper)
   - Adds enrichment/sources/molport_index_build.py (one-time builder)
   - Adds scripts/download_index.py (fetches index from Release asset)
   - Updates molport_scraper.py: pre/post-flight identity checks + stock selector
   - Patches molport_fixtures.py with 3 verified real Molport IDs
     (Molport-006-111-835, Molport-002-317-291, Molport-001-792-501)
   - Expands supplier-row schema: currency, stock_status (in_stock/backorder/
     unknown), is_minimum_order (tagged per supplier-catalogue)
   - Renames price_usd → price (currency now explicit)
   - Extends smoke test to 49 assertions (all passing)
   - .gitignore excludes db_molport_index.sqlite (1.65 GB, hosted as Release asset)
   ```

7. Leave **"Commit directly to the `Clean-4` branch"** selected.
8. Click **Commit changes**.

## Step 4 — Publish the index as a Release asset (after the commit lands)

The 1.65 GB `db_molport_index.sqlite` can't live in git — publish it as
a release asset so `scripts/download_index.py` can fetch it.

1. https://github.com/timbtz/Spherecast-Agnes/releases/new
2. **Tag**: `molport-index-v1` (create new tag on target: `Clean-4`)
3. **Title**: `Molport identity index v1`
4. **Description**:

   ```
   SQLite map of 5,967,425 Molport compounds (SMILES + canonical SMILES → Molport ID).
   Built from Molport's public "All Stock Compounds" SMILES dump.

   Fetch with:
       python scripts/download_index.py

   Size: 1.65 GB. File is static — rebuild quarterly to pick up new compounds.
   ```

5. **Attach binary**: drag `~/Documents/Spherecast-Agnes-phase4/db_molport_index.sqlite`
   onto the "Attach binaries" area. Upload will take 1–3 minutes depending
   on your connection.
6. (Optional) Compute and publish the SHA-256 so downloads can be verified:

   ```bash
   shasum -a 256 ~/Documents/Spherecast-Agnes-phase4/db_molport_index.sqlite
   ```

   Paste the digest at the top of the description.
7. **Target**: `Clean-4` (the branch the tag applies to).
8. Click **Publish release**.

## Step 5 — Smoke-test the release (optional)

Anywhere with Python 3.10+:

```bash
mkdir /tmp/agnes-index-test && cd /tmp/agnes-index-test
curl -sL -o download_index.py \
    https://raw.githubusercontent.com/timbtz/Spherecast-Agnes/Clean-4/scripts/download_index.py
python download_index.py
ls -lh db_molport_index.sqlite    # should show ~1.65 GB
```

Done. Any fresh clone will now be one command away from the full index.

## If something goes wrong

| Symptom | Fix |
|---------|-----|
| Upload preview shows fewer than 10 files | You forgot to reveal hidden files — press ⌘+⇧+. in Finder |
| "File is too large" on the release asset | You're uploading through git, not Releases. Use the Releases web form — it accepts up to 2 GB per asset |
| `download_index.py` 404s | The release tag doesn't match. Default is `molport-index-v1`; override with `--url` or update `DEFAULT_TAG` at the top of the script |
| Smoke test fails with ImportError | You skipped `__init__.py` in the upload — re-upload with that file included |
