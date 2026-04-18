import { useRef, useEffect, Component } from 'react'
import type { ReactNode } from 'react'
import { Orb } from '@/components/ui/orb'
import { useAgnesVoice } from '@/hooks/useAgnesVoice'
import { PIPELINE_COLORS } from '@/types/agnes'
import { PipelineBadge } from './PipelineBadge'

class OrbErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  render() {
    if (this.state.error) return <CssOrbFallback />
    return this.props.children
  }
}

function CssOrbFallback() {
  return <div className="w-full h-full rounded-full bg-slate-700 animate-pulse" />
}

const STATE_LABEL: Record<string, string> = {
  listening: 'Listening…',
  talking: 'Agnes responding…',
}

export function VoiceOrb({ onSpeak }: { onSpeak?: (text: string) => void }) {
  const { agentState, lastPipeline, transcript, inputVolumeRef, outputVolumeRef, startListening } = useAgnesVoice()
  const colors = PIPELINE_COLORS[lastPipeline ?? 'default'] ?? PIPELINE_COLORS.default
  const transcriptTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (transcript) {
      if (transcriptTimeout.current) clearTimeout(transcriptTimeout.current)
    }
  }, [transcript])

  function handleTap() {
    if (agentState === null) startListening()
  }

  const label = agentState === 'thinking'
    ? `Running ${(lastPipeline ?? 'pipeline').replace(/_/g, ' ')}…`
    : agentState
      ? STATE_LABEL[agentState]
      : 'Tap to speak'

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        onClick={handleTap}
        disabled={agentState !== null}
        className="relative h-48 w-48 rounded-full p-2 bg-[#0f1117] shadow-[inset_0_2px_12px_rgba(0,0,0,0.6)] cursor-pointer disabled:cursor-default"
        aria-label={label}
      >
        <div className="h-full w-full overflow-hidden rounded-full">
          <OrbErrorBoundary>
            <Orb
              colors={colors}
              agentState={agentState}
              seed={42}
              inputVolumeRef={inputVolumeRef}
              outputVolumeRef={outputVolumeRef}
            />
          </OrbErrorBoundary>
        </div>
      </button>
      <div className="text-sm text-slate-400">{label}</div>
      {lastPipeline && <PipelineBadge pipeline={lastPipeline} />}
      {transcript && (
        <p className="text-xs text-slate-500 max-w-[180px] text-center truncate">"{transcript}"</p>
      )}
    </div>
  )
}
