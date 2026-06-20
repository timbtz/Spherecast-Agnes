# ui_legacy — INACTIVE

This is the original Agnes voice dashboard, hand-built with Vite + React + Three.js.

**It is NOT started, NOT served, and NOT used.** The active frontend is `orchestration/ui/` (Lovable).

## Why it's kept

Could serve as a fallback if the Lovable frontend is unavailable, or as a reference for component patterns (VoiceOrb, DagPanel, DataExplorer, useAgnesVoice hook).

## To use as fallback

1. Swap the `_UI_DIST` path in `orchestration/api/main.py` to point here
2. Build: `cd orchestration/ui_legacy && pnpm install && pnpm build`
3. Restart FastAPI
