# Clean-4 upload — READ THIS FIRST

Everything is already here in `~/Documents/Clean-4-upload/`. Nothing left to
download or copy. Just upload the contents to GitHub and delete phase-4.

**Do NOT upload this file itself** — `READ-THIS-FIRST.md` is for you, not
the repo.

---

## What's in this folder

```
Clean-4-upload/
├── READ-THIS-FIRST.md                              ← do NOT upload
├── README-phase-4.md                               ← upload
├── .gitignore                                      ← upload
├── Orchestration/
│   └── PRDs/
│       └── PRD-ReasoningScaffold.md                ← upload
├── reasoning/                                      ← upload (12 .py files)
│   ├── __init__.py
│   ├── base.py
│   ├── compliance_reasoner.py
│   ├── consolidation_scorer.py
│   ├── evidence_ledger.py
│   ├── gate_engine.py
│   ├── justification.py
│   ├── proposal_generator.py
│   ├── refusal_engine.py
│   ├── role_inferrer.py
│   ├── substitution_graph.py
│   └── supplier_scorer.py
└── docs/                                           ← upload (6 .md files)
    ├── phase4-package-readme.md
    ├── integration-handoff.md
    ├── missing-data-schema.md
    ├── run-instructions.md
    ├── example-output.md
    └── demo-results.md
```

Total: **21 files**, about **204 KB**.

---

## Step 1 — Make hidden files visible

macOS Finder hides dotfiles. Press **⌘ + ⇧ + .** in Finder while you're
looking at `Clean-4-upload/` to reveal `.gitignore`. (Same shortcut to
hide them again later.)

## Step 2 — Open the Clean-4 branch on GitHub

https://github.com/timbtz/Spherecast-Agnes/tree/Clean-4

Confirm the branch selector in the top-left says **Clean-4** (not `master`,
not `phase-4`).

## Step 3 — Upload

1. Click the green **`Add file`** button → **Upload files**.
2. In Finder, open `~/Documents/Clean-4-upload/`.
3. Select everything **except `READ-THIS-FIRST.md`**:
   - `README-phase-4.md`
   - `.gitignore`
   - `Orchestration/` (folder)
   - `reasoning/` (folder)
   - `docs/` (folder)
4. Drag the selection onto the GitHub upload area. GitHub preserves the
   folder structure — subfolders and all.
5. Scroll down. At the bottom, commit message:
   ```
   feat(Clean-4): reasoning scaffold + docs + PRD, clean layout
   ```
6. Leave **"Commit directly to the `Clean-4` branch"** selected.
7. Click **Commit changes**.

A few seconds later GitHub drops you on the new Clean-4 tree with everything
in place.

## Step 4 — Open the PR

GitHub shows a yellow banner: **"Compare & pull request"**. Click it.

- **Title:** `Clean-4: reasoning scaffold + docs + PRD`
- **Body** (paste):

```
Replaces phase-4. Clean-4 branches off master and adds:
- reasoning/ scaffold (6-gate substitution, compliance reasoner,
  refusal engine, evidence ledger, ToolResult contract).
- docs/ with integration / missing-data / run-instructions / demo-results.
- Orchestration/PRDs/PRD-ReasoningScaffold.md.
- New README-phase-4.md describing the layout.
- .gitignore for python + SQLite + editor caches.

No duplicates, no .env, no binary DBs, no __pycache__.
phase-4 branch will be deleted once this lands.
```

Click **Create pull request**.

## Step 5 — Delete phase-4 (after the PR merges)

1. https://github.com/timbtz/Spherecast-Agnes/branches
2. Find `phase-4` in the list.
3. Click the trash icon on the right. Confirm.

## Step 6 — Rotate the leaked keys

`.env` sat in phase-4's git history. Treat these as exposed and rotate:

- `ANTHROPIC_API_KEY` — https://console.anthropic.com/settings/keys
- `GOOGLE_API_KEY` — https://aistudio.google.com/app/apikey
- `DSLD_API_KEY` — re-issue via the DSLD API portal
- Any Molport / USDA FDC / openFDA keys that were in there

Put the new keys in your local `.env` (now gitignored) and keep them out of
version control.

---

## If something goes wrong

| Symptom                                             | Fix                                                        |
| --------------------------------------------------- | ---------------------------------------------------------- |
| Upload stalls halfway                               | Cancel, upload `reasoning/` alone, then the rest as a 2nd commit |
| `.env` appears in the file picker                   | Close picker, verify `Clean-4-upload/.env` doesn't exist (it shouldn't) |
| `__pycache__/` appears in the preview               | Cancel; confirm `reasoning/__pycache__/` was not included   |
| GitHub says "You need write access"                 | Ask timbtz to add `gursagar-singhs` as a collaborator      |
| Preview shows changes to unexpected files on master | You're on the wrong branch — reopen on `/tree/Clean-4`     |
