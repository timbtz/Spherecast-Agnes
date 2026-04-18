# REF: ElevenLabs Orb UI Component

**Source:** ElevenLabs open-source UI component library  
**Install:** `pnpm dlx @elevenlabs/cli@latest components add orb`  
**Deps:** Three.js, React Three Fiber, `@react-three/fiber`, `@react-three/drei`  
**License:** Apache 2.0 (open source)

---

## What It Is

A WebGL 3D sphere rendered in a `<canvas>` via React Three Fiber and custom GLSL shaders. It visually reacts to:
- Audio input/output volume (float 0–1)
- Agent state transitions (`null` | `"listening"` | `"thinking"` | `"talking"`)

It is a **pure visual component** — no audio capture, no API calls, no ElevenLabs SDK dependency. You wire it to whatever audio/state machinery you have.

---

## Installation

```bash
# 1. Install CLI and add component
pnpm dlx @elevenlabs/cli@latest components add orb

# Outputs: src/components/ui/orb.tsx (or @/components/ui/orb)

# 2. Install peer deps if not already present
pnpm add three @react-three/fiber @react-three/drei
```

The component is copied into your project (not a node_modules import). You own the code.

---

## Props API

| Prop | Type | Default | Description |
|---|---|---|---|
| `colors` | `[string, string]` | `["#CADCFC", "#A0B9D1"]` | Gradient start/end hex or CSS color |
| `colorsRef` | `RefObject<[string, string]>` | — | Ref for dynamic color updates without re-render |
| `seed` | `number` | Random | Integer seed for deterministic animation pattern |
| `agentState` | `AgentState` | `null` | Visual mode: `null` (idle), `"listening"`, `"thinking"`, `"talking"` |
| `volumeMode` | `"auto" \| "manual"` | `"auto"` | `"auto"` = call the getter fns each frame; `"manual"` = read `manualInput`/`manualOutput` |
| `manualInput` | `number` | — | 0–1 input volume (only used in `"manual"` mode) |
| `manualOutput` | `number` | — | 0–1 output volume (only used in `"manual"` mode) |
| `inputVolumeRef` | `RefObject<number>` | — | Ref for input volume (zero-copy hot-path) |
| `outputVolumeRef` | `RefObject<number>` | — | Ref for output volume (zero-copy hot-path) |
| `getInputVolume` | `() => number` | — | Called each animation frame in `"auto"` mode |
| `getOutputVolume` | `() => number` | — | Called each animation frame in `"auto"` mode |
| `resizeDebounce` | `number` | `100` | Canvas resize debounce (ms) |
| `className` | `string` | — | CSS class applied to the canvas container |

### AgentState type
```typescript
type AgentState = null | "thinking" | "listening" | "talking"
```

### Visual behavior per state
| State | Visual effect |
|---|---|
| `null` (idle) | Slow, calm undulation |
| `"listening"` | Pulses in response to `inputVolume` |
| `"thinking"` | Faster, complex shader pattern |
| `"talking"` | Pulses in response to `outputVolume` |

---

## Basic Usage

```tsx
import { Orb } from "@/components/ui/orb"

// Static idle orb
<Orb />

// Custom colors
<Orb colors={["#FF6B6B", "#4ECDC4"]} />

// Controlled state (e.g. wired to your voice pipeline)
const [agentState, setAgentState] = useState<AgentState>(null)
<Orb agentState={agentState} />
```

---

## Audio Volume Wiring Patterns

### Pattern A: Callback functions (simple)
```tsx
function VoiceOrb() {
  // Your audio analysis returns 0–1 values
  const getInputVolume = () => micAnalyser.getVolume()
  const getOutputVolume = () => speakerAnalyser.getVolume()

  return (
    <Orb
      getInputVolume={getInputVolume}
      getOutputVolume={getOutputVolume}
    />
  )
}
```

### Pattern B: Refs (high-frequency, zero re-render)
```tsx
function VoiceOrb() {
  const inputVolumeRef = useRef(0)
  const outputVolumeRef = useRef(0)

  // Update from audio worklet or requestAnimationFrame
  useEffect(() => {
    const id = setInterval(() => {
      inputVolumeRef.current = micAnalyser.getVolume()
      outputVolumeRef.current = speakerAnalyser.getVolume()
    }, 16)
    return () => clearInterval(id)
  }, [])

  return (
    <Orb
      volumeMode="auto"
      inputVolumeRef={inputVolumeRef}
      outputVolumeRef={outputVolumeRef}
    />
  )
}
```

### Pattern C: Manual / state-driven (no real audio)
```tsx
// Drive volume purely from pipeline state (no mic)
const [inputVol, setInputVol] = useState(0)
const [outputVol, setOutputVol] = useState(0)

<Orb
  volumeMode="manual"
  manualInput={inputVol}
  manualOutput={outputVol}
/>
```

---

## Wrapping the Orb (Agnes Design Pattern)

The ElevenLabs demo shows the Orb inside a circular container with a subtle inner shadow:

```tsx
<div className="relative h-40 w-40 rounded-full p-1
    bg-[#1a202c] shadow-[inset_0_2px_8px_rgba(0,0,0,0.5)]">
  <div className="h-full w-full overflow-hidden rounded-full
      shadow-[inset_0_0_12px_rgba(0,0,0,0.3)]">
    <Orb
      colors={["#CADCFC", "#A0B9D1"]}
      agentState={agentState}
      seed={1000}
    />
  </div>
</div>
```

For Agnes, consider these color palettes per pipeline:
| Pipeline | Colors | Reasoning |
|---|---|---|
| Idle | `["#CADCFC", "#A0B9D1"]` | Default calm blue-grey |
| Supplier fallout | `["#FEB2B2", "#FC8181"]` | Red tones = urgency |
| Consolidation | `["#9AE6B4", "#68D391"]` | Green = opportunity |
| Research | `["#D6BCFA", "#B794F4"]` | Purple = exploration |
| Price audit | `["#FAF089", "#F6E05E"]` | Yellow = financial |

---

## Performance Notes

- WebGL canvas; uses `requestAnimationFrame` internally via React Three Fiber
- Proper cleanup on unmount — no memory leaks
- `colorsRef` prop avoids re-renders when changing colors dynamically (prefer over `colors` in hot loops)
- Do not render more than 3–4 Orb instances simultaneously on one page

---

## Gotchas

- Requires a React client-side context (`"use client"` in Next.js)
- The `seed` prop controls the animation's starting variation — use a fixed seed for consistent appearance per agent persona
- `volumeMode="auto"` calls your getter functions **every animation frame** (~60fps) — keep them cheap (no async, no state reads)
- Canvas resizes are debounced; set `resizeDebounce={0}` for instant resize if needed in layout animations
