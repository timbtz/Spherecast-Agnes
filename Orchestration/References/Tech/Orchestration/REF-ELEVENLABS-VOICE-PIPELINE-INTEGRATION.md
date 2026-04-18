# REF: ElevenLabs Voice ↔ Agnes Pipeline Integration

**Scope:** Wiring ElevenLabs voice (STT + TTS) to the Agnes orchestration layer (`POST /chat` → SSE stream → spoken response), with the Orb UI component as the visual interface.  
**Related:** `REF-ELEVENLABS-ORB-UI.md`, `5. OrchestrationLayerStatus.md`, `REF-SSE-STREAMING-FASTAPI.md`

---

## Architecture Overview

```
User speaks
    │
    ▼
[Orb UI — agentState="listening"]
    │  (Web Audio API captures mic)
    ▼
ElevenLabs STT  ──or──  Web Speech API (SpeechRecognition)
    │  transcript (string)
    ▼
POST /chat  { message: transcript }
    │  returns { run_id, pipeline, status: "started" }
    ▼
[Orb UI — agentState="thinking"]
    │
    ▼
GET /runs/{run_id}/stream  (SSE)
    │  node events stream in real-time
    │  (optional: narrate each node via TTS as it completes)
    ▼
pipeline_completed event → extract final proposal text
    │
    ▼
ElevenLabs TTS  POST to voice synthesis
    │  audio stream
    ▼
[Orb UI — agentState="talking"]
    │  AudioContext plays response audio
    ▼
Orb returns to idle (agentState=null)
```

---

## Approach Options

### Option 1 — Custom STT + ElevenLabs TTS (Recommended for Agnes v1)

You handle STT yourself (browser Web Speech API or ElevenLabs STT), call Agnes `/chat` directly, and use ElevenLabs TTS to speak the result.

**Pros:** Full control of pipeline routing, works with your existing FastAPI backend, no ElevenLabs agent setup needed.  
**Cons:** Must implement STT fallback (browser API inconsistent across browsers).

### Option 2 — ElevenLabs Conversational AI Agent with Webhook Tool

Create an ElevenLabs Conversational AI agent in the dashboard. Define a custom "tool" that the agent calls (your `/chat` endpoint). ElevenLabs handles STT/TTS/turn-taking; Agnes handles pipeline execution.

**Pros:** Production-grade STT, natural multi-turn conversation, ElevenLabs manages audio plumbing.  
**Cons:** Requires ElevenLabs API key, agent dashboard setup, and your `/chat` endpoint must be publicly reachable (or tunneled via ngrok for local dev).

---

## Option 1 Implementation: Custom STT + ElevenLabs TTS

### 1.1 Dependencies

```bash
# React frontend (add to your Agnes UI)
pnpm add elevenlabs @react-three/fiber @react-three/drei three

# Or vanilla JS — elevenlabs has a browser bundle
```

### 1.2 ElevenLabs TTS API

```typescript
// POST to ElevenLabs TTS — returns audio stream
async function synthesizeSpeech(text: string, voiceId: string): Promise<ArrayBuffer> {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/stream`,
    {
      method: "POST",
      headers: {
        "xi-api-key": process.env.NEXT_PUBLIC_ELEVENLABS_API_KEY!,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        model_id: "eleven_turbo_v2_5",   // lowest latency
        voice_settings: { stability: 0.5, similarity_boost: 0.75 },
      }),
    }
  )
  return res.arrayBuffer()
}
```

**Voice IDs** — find in ElevenLabs dashboard → Voices. Recommended for Agnes:
- `21m00Tcm4TlvDq8ikWAM` — Rachel (clear, professional)
- `AZnzlk1XvdvUeBnXmlld` — Domi (energetic, analyst feel)

### 1.3 STT: Browser Web Speech API (dev/demo)

```typescript
function useSpeechRecognition(onResult: (transcript: string) => void) {
  const recognitionRef = useRef<SpeechRecognition | null>(null)

  const start = () => {
    const SpeechRecognition =
      window.SpeechRecognition || (window as any).webkitSpeechRecognition
    const rec = new SpeechRecognition()
    rec.continuous = false
    rec.interimResults = false
    rec.lang = "en-US"
    rec.onresult = (e) => onResult(e.results[0][0].transcript)
    rec.start()
    recognitionRef.current = rec
  }

  const stop = () => recognitionRef.current?.stop()
  return { start, stop }
}
```

### 1.4 SSE Event Consumption

```typescript
function useRunStream(runId: string | null, onEvent: (ev: PipelineEvent) => void) {
  useEffect(() => {
    if (!runId) return
    const es = new EventSource(`http://localhost:8000/runs/${runId}/stream`)
    es.onmessage = (e) => {
      const event = JSON.parse(e.data) as PipelineEvent
      onEvent(event)
      if (event.event_type === "stream_closed") es.close()
    }
    return () => es.close()
  }, [runId])
}

interface PipelineEvent {
  event_type: string   // node_started | node_completed | node_skipped | pipeline_completed | pipeline_failed | stream_closed
  node_id?: string
  node_output?: Record<string, unknown>
  error?: string
  created_at: string
}
```

### 1.5 Extracting the Final Answer

The `write-proposal` node in `supplier_fallout` outputs `proposal_text`. Other pipelines vary:

```typescript
function extractAnswer(events: PipelineEvent[]): string | null {
  for (const ev of events.reverse()) {
    if (ev.event_type === "node_completed" && ev.node_output) {
      const out = ev.node_output as Record<string, unknown>
      // supplier_fallout → write-proposal
      if (out.proposal_text) return out.proposal_text as string
      // proactive_consolidation → write-proposals
      if (out.proposals_narrative) return out.proposals_narrative as string
      // fallback: stringify first meaningful output
      const keys = Object.keys(out)
      if (keys.length > 0) return JSON.stringify(out[keys[0]], null, 2)
    }
  }
  return null
}
```

### 1.6 Complete Agnes Voice Hook

```typescript
import { useState, useRef, useCallback } from "react"
import type { AgentState } from "@/components/ui/orb"

const AGNES_API = "http://localhost:8000"
const ELEVENLABS_KEY = process.env.NEXT_PUBLIC_ELEVENLABS_API_KEY!
const VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

export function useAgnesVoice() {
  const [agentState, setAgentState] = useState<AgentState>(null)
  const [lastPipeline, setLastPipeline] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<string>("")
  const outputVolRef = useRef(0)
  const inputVolRef = useRef(0)

  const speak = useCallback(async (text: string) => {
    setAgentState("talking")
    const res = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream`,
      {
        method: "POST",
        headers: { "xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          model_id: "eleven_turbo_v2_5",
          voice_settings: { stability: 0.5, similarity_boost: 0.75 },
        }),
      }
    )
    const audioCtx = new AudioContext()
    const buffer = await res.arrayBuffer()
    const decoded = await audioCtx.decodeAudioData(buffer)
    const source = audioCtx.createBufferSource()
    source.buffer = decoded
    // Analyser for Orb output volume
    const analyser = audioCtx.createAnalyser()
    source.connect(analyser)
    analyser.connect(audioCtx.destination)
    source.start()
    // Feed volume to Orb ref
    const data = new Float32Array(analyser.frequencyBinCount)
    const updateVol = () => {
      analyser.getFloatTimeDomainData(data)
      const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length)
      outputVolRef.current = Math.min(rms * 4, 1)
      if (agentState === "talking") requestAnimationFrame(updateVol)
    }
    updateVol()
    source.onended = () => {
      outputVolRef.current = 0
      setAgentState(null)
    }
  }, [agentState])

  const runPipeline = useCallback(async (message: string) => {
    setAgentState("thinking")
    setTranscript(message)

    // 1. Route to pipeline
    const chatRes = await fetch(`${AGNES_API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, user_id: "voice-user" }),
    }).then(r => r.json())

    if (chatRes.status === "no_match") {
      await speak("I couldn't determine which pipeline to run for that request. Could you rephrase?")
      return
    }

    setLastPipeline(chatRes.pipeline)

    // Optional: narrate pipeline start
    await speak(`Running the ${chatRes.pipeline.replace(/_/g, " ")} pipeline.`)
    setAgentState("thinking")

    // 2. Subscribe to SSE stream
    const events: PipelineEvent[] = []
    await new Promise<void>((resolve) => {
      const es = new EventSource(`${AGNES_API}/runs/${chatRes.run_id}/stream`)
      es.onmessage = async (e) => {
        const ev = JSON.parse(e.data) as PipelineEvent
        events.push(ev)

        // Optional: narrate node completions
        if (ev.event_type === "node_completed" && ev.node_id) {
          // Could speak a brief status: "Checking compliance..." etc.
        }

        if (ev.event_type === "pipeline_completed" || ev.event_type === "pipeline_failed") {
          es.close()
          resolve()
        }
        if (ev.event_type === "stream_closed") {
          es.close()
          resolve()
        }
      }
      es.onerror = () => { es.close(); resolve() }
    })

    // 3. Extract and speak final answer
    const answer = extractAnswer(events)
    if (answer) {
      await speak(answer)
    } else {
      await speak("The pipeline completed but I couldn't extract a spoken summary.")
    }
  }, [speak])

  const startListening = useCallback(() => {
    setAgentState("listening")
    const SpeechRec = window.SpeechRecognition || (window as any).webkitSpeechRecognition
    const rec = new SpeechRec()
    rec.continuous = false
    rec.lang = "en-US"
    rec.onresult = (e: SpeechRecognitionEvent) => {
      const t = e.results[0][0].transcript
      inputVolRef.current = 0
      runPipeline(t)
    }
    rec.onerror = () => setAgentState(null)
    rec.start()
  }, [runPipeline])

  return {
    agentState,
    lastPipeline,
    transcript,
    inputVolumeRef: inputVolRef,
    outputVolumeRef: outputVolRef,
    startListening,
  }
}
```

### 1.7 Agnes Voice UI Component

```tsx
"use client"
import { Orb } from "@/components/ui/orb"
import { useAgnesVoice } from "@/hooks/useAgnesVoice"

const PIPELINE_COLORS: Record<string, [string, string]> = {
  supplier_fallout:        ["#FEB2B2", "#FC8181"],
  proactive_consolidation: ["#9AE6B4", "#68D391"],
  new_ingredient_research: ["#D6BCFA", "#B794F4"],
  price_audit:             ["#FAF089", "#F6E05E"],
  substitution_discovery:  ["#FBD38D", "#F6AD55"],
  default:                 ["#CADCFC", "#A0B9D1"],
}

export function AgnesVoiceOrb() {
  const { agentState, lastPipeline, transcript, inputVolumeRef, outputVolumeRef, startListening } =
    useAgnesVoice()

  const colors = PIPELINE_COLORS[lastPipeline ?? "default"] ?? PIPELINE_COLORS.default

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Orb */}
      <button
        onClick={agentState === null ? startListening : undefined}
        className="relative h-48 w-48 rounded-full p-2 bg-[#0f1117]
          shadow-[inset_0_2px_12px_rgba(0,0,0,0.6)] cursor-pointer"
      >
        <div className="h-full w-full overflow-hidden rounded-full">
          <Orb
            colors={colors}
            agentState={agentState}
            seed={42}
            volumeMode="auto"
            inputVolumeRef={inputVolumeRef}
            outputVolumeRef={outputVolumeRef}
          />
        </div>
      </button>

      {/* State label */}
      <div className="text-sm text-slate-400">
        {agentState === null && "Tap to speak"}
        {agentState === "listening" && "Listening..."}
        {agentState === "thinking" && `Running ${lastPipeline?.replace(/_/g, " ") ?? "pipeline"}...`}
        {agentState === "talking" && "Agnes responding..."}
      </div>

      {/* Last transcript */}
      {transcript && (
        <p className="text-xs text-slate-500 max-w-xs text-center">"{transcript}"</p>
      )}
    </div>
  )
}
```

---

## Option 2 Implementation: ElevenLabs Conversational AI Agent

### 2.1 Concept

ElevenLabs hosts a voice agent that:
1. Accepts phone/web calls
2. Runs STT on speech
3. Can call external tools (HTTP webhooks) — this is where you call Agnes
4. Synthesizes responses with high-quality TTS
5. Manages turn-taking and interruption handling

### 2.2 ElevenLabs Agent Setup (Dashboard)

1. Go to **ElevenLabs → Conversational AI → Agents → New Agent**
2. **System prompt:** "You are Agnes, a supply chain intelligence assistant. When users ask about supplier issues, consolidation opportunities, or pricing, call the `run_agnes_pipeline` tool and relay the results."
3. **Tools → Add Tool:**
   - Name: `run_agnes_pipeline`
   - Description: "Triggers an Agnes supply chain analysis pipeline and returns the result"
   - Method: `POST`
   - URL: `https://your-domain/chat`  (or ngrok tunnel for local dev)
   - Body schema: `{ "message": "{user_message}" }`
4. **Voice:** Select voice, configure latency vs quality tradeoff

### 2.3 ElevenLabs React SDK (`@11labs/react`)

```bash
pnpm add @11labs/react
```

```tsx
"use client"
import { useConversation } from "@11labs/react"
import { Orb } from "@/components/ui/orb"
import { useState, useRef } from "react"
import type { AgentState } from "@/components/ui/orb"

const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID!

export function AgnesConversationalOrb() {
  const [agentState, setAgentState] = useState<AgentState>(null)
  const outputVolRef = useRef(0)
  const inputVolRef = useRef(0)

  const conversation = useConversation({
    agentId: AGENT_ID,
    onConnect: () => setAgentState("listening"),
    onDisconnect: () => setAgentState(null),
    onMessage: (msg) => {
      if (msg.type === "agent_response") setAgentState("talking")
      if (msg.type === "user_transcript") setAgentState("thinking")
    },
    onError: (err) => { console.error(err); setAgentState(null) },
  })

  const toggle = async () => {
    if (conversation.status === "connected") {
      await conversation.endSession()
    } else {
      await conversation.startSession()
    }
  }

  return (
    <button onClick={toggle} className="h-48 w-48 rounded-full p-2 bg-[#0f1117]">
      <div className="h-full w-full overflow-hidden rounded-full">
        <Orb
          agentState={agentState}
          seed={42}
          inputVolumeRef={inputVolRef}
          outputVolumeRef={outputVolRef}
        />
      </div>
    </button>
  )
}
```

### 2.4 Making `/chat` Publicly Reachable (Local Dev)

```bash
# Option A: ngrok
ngrok http 8000
# Use the https tunnel URL in ElevenLabs tool config

# Option B: cloudflared (Cloudflare tunnel, free)
cloudflared tunnel --url http://localhost:8000
```

---

## Step-by-Step Node Narration (Optional Enhancement)

For a richer experience, Agnes can narrate pipeline progress as nodes complete. Map `node_id` to human-readable status lines:

```typescript
const NODE_NARRATION: Record<string, string> = {
  "find-alternatives":   "Finding alternative suppliers...",
  "gate-qualify":        "Checking compliance requirements...",
  "bom-impact":          "Analyzing affected products...",
  "format-rfqs":         "Preparing supplier quotes...",
  "write-proposal":      "Writing the final recommendation...",
  "scan-opportunities":  "Scanning consolidation opportunities...",
  "benchmark-prices":    "Benchmarking current pricing...",
  "walk-substitutions":  "Exploring ingredient substitutions...",
}

// In SSE handler:
if (ev.event_type === "node_started" && ev.node_id) {
  const narration = NODE_NARRATION[ev.node_id]
  if (narration) await speak(narration)  // short clip between nodes
}
```

This makes the Orb feel like a live analyst working through the problem step by step.

---

## Environment Variables Needed

```bash
# .env (frontend)
NEXT_PUBLIC_ELEVENLABS_API_KEY=sk-...       # ElevenLabs API key
NEXT_PUBLIC_ELEVENLABS_AGENT_ID=agent_...   # Only for Option 2 (Conversational AI)
NEXT_PUBLIC_AGNES_API_URL=http://localhost:8000

# .env (Agnes backend — already exists)
ANTHROPIC_API_KEY=...
```

To get your ElevenLabs API key: **ElevenLabs Dashboard → Profile → API Keys**

---

## Integration Into Existing Agnes UI (`orchestration/ui/index.html`)

The current UI is vanilla HTML/JS. To add the Orb (which requires React + WebGL), two options:

### Option A: React Island (Recommended)

Add a React app just for the voice orb widget, mount it into the existing page:

```html
<!-- In index.html, add a mount point -->
<div id="voice-orb-root"></div>
<script type="module" src="/voice-orb/main.jsx"></script>
```

The React mini-app renders `<AgnesVoiceOrb />` into that div.

### Option B: New Page

Create `orchestration/ui/voice.html` as a separate full React/Next.js page. Link from the existing monitor header. Simpler separation of concerns.

**Recommended:** Option B — the existing monitor UI uses Alpine.js + vanilla JS; mixing React into it is messy. A dedicated `/voice` page keeps them separate.

---

## Recommended Build Setup for Voice UI

```
orchestration/
  ui/
    index.html           ← existing DAG monitor (keep as-is)
    voice/
      package.json       ← Vite + React
      src/
        main.tsx
        App.tsx
        components/
          AgnesVoiceOrb.tsx
        hooks/
          useAgnesVoice.ts
```

```bash
cd orchestration/ui/voice
pnpm create vite . --template react-ts
pnpm add elevenlabs @react-three/fiber @react-three/drei three
pnpm dlx @elevenlabs/cli@latest components add orb
pnpm dev   # runs on :5173
```

Then in `orchestration/api/main.py`, also serve the built voice UI:
```python
_VOICE_UI_DIR = Path(__file__).parent.parent / "ui" / "voice" / "dist"
if _VOICE_UI_DIR.exists():
    app.mount("/voice", StaticFiles(directory=str(_VOICE_UI_DIR), html=True), name="voice-ui")
```

---

## Key ElevenLabs Resources

| Resource | URL |
|---|---|
| TTS API docs | https://elevenlabs.io/docs/api-reference/text-to-speech |
| Conversational AI docs | https://elevenlabs.io/docs/conversational-ai/overview |
| `@11labs/react` SDK | https://elevenlabs.io/docs/conversational-ai/libraries/react |
| ElevenLabs Dashboard | https://elevenlabs.io/app |
| Voice library | https://elevenlabs.io/voice-library |
| Orb component source | Copied to your project by CLI — `src/components/ui/orb.tsx` |

---

## Summary: Recommended Agnes v1 Integration Path

1. **Start with Option 1** (custom STT + ElevenLabs TTS) — no ElevenLabs agent setup, works fully offline except TTS call
2. Use **Web Speech API** for STT in demo/dev; upgrade to ElevenLabs STT or Whisper for production
3. Build the voice UI as a **separate Vite+React page** at `/voice`
4. Wire the **Orb `agentState`** to: `listening` (mic open) → `thinking` (pipeline running) → `talking` (TTS playing)
5. **Step narration** per node is optional but makes Agnes feel alive — add after the basic loop works
6. **Migrate to Option 2** (Conversational AI) when you want multi-turn conversations, better STT, and interruption handling
