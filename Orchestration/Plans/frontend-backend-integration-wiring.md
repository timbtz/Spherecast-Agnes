# Feature: Frontend–Backend Integration Wiring

> The following plan is complete, but validate file paths and field names against the current state before executing each task.

## Feature Description

The Lovable frontend (`orchestration/ui/`) is fully built and served by FastAPI at `/`. All endpoints exist and match. However, three wiring bugs prevent end-to-end voice pipeline operation: a critical request body field mismatch (`text` vs `message`) that breaks every chat call, and missing `summary` fields in backend agent outputs that prevent the voice orb from speaking pipeline results.

## User Story

As a procurement manager using Agnes  
I want to speak a question and hear Agnes respond  
So that I get hands-free supply chain intelligence through the voice orb

## Problem Statement

The Lovable frontend sends `{ text }` to `POST /chat` but the backend `ChatRequest` model expects `{ message }`. Every voice interaction fails silently (API call 422s, frontend falls back to demo mode). Additionally, `extractSpokenResponse()` on the frontend searches `node_output.summary` and `node_output.proposal_text` — but reactive/proactive/research agents emit `narrative`, `proposals`, and `discovered_suppliers` respectively, never `summary`. The voice orb will always speak the fallback "Agnes finished the pipeline but produced no narrative response."

## Solution Statement

Fix the field name in `agnesApi.ts`. Add a `summary` field to each backend agent's return dict (alias of whatever the agent's main text output is). Set the ElevenLabs API key in `orchestration/ui/.env`. Rebuild and verify.

## Feature Metadata

**Feature Type**: Bug Fix  
**Estimated Complexity**: Low  
**Primary Systems Affected**: `agnesApi.ts`, 3 backend agent files  
**Dependencies**: ElevenLabs API key (for TTS; demo mode works without it)

---

## CONTEXT REFERENCES

### Files to Read Before Implementing

- `orchestration/ui/src/lib/agnesApi.ts` (line 70) — sends `{ text }` ← **the bug**
- `orchestration/api/routes/chat.py` (lines 14–15) — `ChatRequest.message: str`
- `orchestration/ui/src/store/agnesStore.ts` (lines 125–140) — `extractSpokenResponse` looks for `node_output.summary` then `node_output.proposal_text`
- `orchestration/agents/reactive_agent.py` (lines 46–52) — returns `narrative`, not `summary`
- `orchestration/agents/proactive_agent.py` (lines 34–49) — returns `proposals`, not `summary`
- `orchestration/agents/research_agent.py` (lines 48–56) — returns `discovered_suppliers`, not `summary`
- `orchestration/agents/proposal_writer.py` (lines 72–75) — ✅ already returns `proposal_text` (frontend finds this)
- `orchestration/ui/.env` — already has `VITE_AGNES_API_URL=http://localhost:8000` and `VITE_ELEVENLABS_VOICE_ID`

### Endpoint Coverage (Already Verified ✅)

All frontend calls have matching backend routes. No missing endpoints. Only the chat body field name and agent output keys need fixing.

---

## IMPLEMENTATION PLAN

### Phase 1: Fix Critical Chat Body Bug

`agnesApi.ts` line 70 sends `{ text }` — backend rejects it with 422.

### Phase 2: Add summary field to agent outputs

`extractSpokenResponse` walks `node_output.summary` first. Agents currently emit `narrative` / `proposals` / `discovered_suppliers`. Adding `"summary"` as an alias requires one-line changes per agent.

### Phase 3: ElevenLabs API key

Already templated in `.env`. User fills in key; no code change needed.

### Phase 4: Rebuild and validate

`bun run build` from `orchestration/ui/`, restart FastAPI, run manual voice test.

---

## STEP-BY-STEP TASKS

### TASK 1: UPDATE `orchestration/ui/src/lib/agnesApi.ts` — fix chat body field name

- **FIX**: Line 70 — change `JSON.stringify({ text })` → `JSON.stringify({ message: text })`
- **VALIDATE**: `grep -n '"message"\|"text"' orchestration/ui/src/lib/agnesApi.ts` — should show `message: text`, not `{ text }`

### TASK 2: UPDATE `orchestration/agents/reactive_agent.py` — add summary alias

- **FIX**: In the `return {...}` dict (line 46), add `"summary": narrative,` as the first key
- **PATTERN**: `reactive_agent.py:42` — `narrative` is the variable holding the LLM text output
- **VALIDATE**: `python -c "from orchestration.agents.reactive_agent import run; print('ok')"` (PYTHONPATH=.)

### TASK 3: UPDATE `orchestration/agents/proactive_agent.py` — add summary alias

- **FIX**: In the final `return {...}` dict (line 46), add `"summary": f"Identified {count} consolidation opportunities."` (or compose from the proposals list)
- **VALIDATE**: `python -c "from orchestration.agents.proactive_agent import run; print('ok')"` (PYTHONPATH=.)

### TASK 4: UPDATE `orchestration/agents/research_agent.py` — add summary alias

- **FIX**: In the final `return {...}` dict, add `"summary": f"Found {count} suppliers for {ingredient_name}."` composed from existing return fields
- **VALIDATE**: `python -c "from orchestration.agents.research_agent import run; print('ok')"` (PYTHONPATH=.)

### TASK 5: SET `VITE_ELEVENLABS_API_KEY` in `orchestration/ui/.env`

- **ACTION**: Fill in `VITE_ELEVENLABS_API_KEY=<your key>` (already templated)
- **OPTIONAL**: If no key, demo mode fallback still shows transcript — just no spoken audio
- **VALIDATE**: `grep VITE_ELEVENLABS_API_KEY orchestration/ui/.env`

### TASK 6: REBUILD frontend

- **RUN**: `cd orchestration/ui && bun run build`
- **VALIDATE**: `ls orchestration/ui/dist/index.html` — must exist

### TASK 7: RESTART FastAPI and smoke-test

- **RUN**: `PYTHONPATH=. uvicorn orchestration.api.main:app --reload --port 8000`
- **VALIDATE**: `curl -s http://localhost:8000/health` → `{"status":"ok"}`
- **VALIDATE**: `curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"message":"What are my top consolidation opportunities?"}' | python3 -m json.tool`  
  → should return `{run_id, pipeline, status, ...}` (not 422)

---

## TESTING STRATEGY

### Manual Voice Test (golden path)

1. Open `http://localhost:8000` in Chrome or Edge (required for Web Speech API)
2. Click the orb to start listening
3. Say: *"What are my top consolidation opportunities?"*
4. Orb transitions: idle → listening → thinking → talking
5. Agnes speaks the pipeline result (or shows transcript if no ElevenLabs key)

### Manual Demo Mode Test (no API key needed)

1. Stop FastAPI server
2. Open `http://localhost:8000` — frontend should auto-flip to demo mode
3. Voice input should still work with mocked responses

### API Smoke Tests

```bash
# Health
curl -s http://localhost:8000/health

# Chat (critical fix validation)
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"show me opportunities"}' | python3 -m json.tool

# Data endpoints
curl -s http://localhost:8000/api/data/opportunities | python3 -m json.tool
curl -s http://localhost:8000/api/data/ingredients | python3 -m json.tool

# Pipeline list
curl -s http://localhost:8000/pipelines | python3 -m json.tool
```

---

## ACCEPTANCE CRITERIA

- [ ] `POST /chat` with `{"message":"..."}` returns 200 with `{run_id, pipeline, status}` (not 422)
- [ ] Voice orb transitions through listening → thinking → talking on a real question
- [ ] `extractSpokenResponse` returns agent text (not the fallback string) after pipeline completes
- [ ] `http://localhost:8000` serves the Lovable UI (not FastAPI JSON root)
- [ ] `/health` still returns 200 (API routes take priority over SPA catch-all)
- [ ] All data tabs (Opportunities, Ingredients, Compliance, Proposals) load real data

---

## NOTES

**Demo mode**: `agnesApi.ts` auto-flips to demo on first network failure — useful for design iteration without a running backend. This is already implemented in Lovable.

**ElevenLabs without key**: `isElevenLabsConfigured()` returns false → `speak()` sets orb to idle without audio. The transcript still shows in the UI. Functional demo without TTS.

**`proposal_writer` already works**: It returns `{ proposal_text }` which `extractSpokenResponse` finds on the second pass. The `proactive_consolidation` pipeline will already speak correctly once the chat bug is fixed.

**Voice browser support**: Web Speech API requires Chrome or Edge. Safari and Firefox will show the "Voice input not supported" error — expected behavior.

**Syncing Lovable changes**: `./pull-ui.sh` — runs `git subtree pull`, `bun install`, `bun run build`. The `.env` file is gitignored and persists across pulls.
