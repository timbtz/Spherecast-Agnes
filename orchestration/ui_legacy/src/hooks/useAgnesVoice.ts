import { useState, useRef, useCallback } from 'react'
import type { AgentState, PipelineEvent } from '@/types/agnes'
import { extractAnswer } from '@/lib/extractAnswer'
import { useRunStore } from '@/store/runStore'

const AGNES_API = import.meta.env.VITE_AGNES_API_URL ?? 'http://localhost:8001'
const ELEVENLABS_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY ?? ''
const VOICE_ID = import.meta.env.VITE_ELEVENLABS_VOICE_ID ?? '21m00Tcm4TlvDq8ikWAM'

export function useAgnesVoice() {
  const [agentState, setAgentState] = useState<AgentState>(null)
  const [lastPipeline, setLastPipeline] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<string>('')
  const outputVolRef = useRef(0)
  const inputVolRef = useRef(0)
  const { setActiveRun, updateNode } = useRunStore()

  const speak = useCallback(async (text: string) => {
    setAgentState('talking')
    if (!ELEVENLABS_KEY) {
      await new Promise<void>(resolve => setTimeout(resolve, 1500))
      setAgentState(null)
      return
    }
    try {
      const res = await fetch(
        `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream`,
        {
          method: 'POST',
          headers: { 'xi-api-key': ELEVENLABS_KEY, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text,
            model_id: 'eleven_turbo_v2_5',
            voice_settings: { stability: 0.5, similarity_boost: 0.75 },
          }),
        }
      )
      const audioCtx = new AudioContext()
      const buffer = await res.arrayBuffer()
      const decoded = await audioCtx.decodeAudioData(buffer)
      const source = audioCtx.createBufferSource()
      source.buffer = decoded
      const analyser = audioCtx.createAnalyser()
      source.connect(analyser)
      analyser.connect(audioCtx.destination)
      source.start()
      const data = new Float32Array(analyser.frequencyBinCount)
      const tick = () => {
        analyser.getFloatTimeDomainData(data)
        const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length)
        outputVolRef.current = Math.min(rms * 4, 1)
        if (agentState === 'talking') requestAnimationFrame(tick)
      }
      tick()
      await new Promise<void>(resolve => { source.onended = () => { outputVolRef.current = 0; resolve() } })
    } catch {
    }
    setAgentState(null)
  }, [])

  const runPipeline = useCallback(async (message: string) => {
    setAgentState('thinking')
    setTranscript(message)
    try {
      const chatRes = await fetch(`${AGNES_API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, user_id: 'voice-user' }),
      }).then(r => r.json())

      if (chatRes.status === 'no_match') {
        await speak("I couldn't determine which pipeline to run. Could you rephrase?")
        return
      }

      setLastPipeline(chatRes.pipeline)
      setActiveRun(chatRes.run_id, chatRes.pipeline)

      const events: PipelineEvent[] = []
      await new Promise<void>((resolve) => {
        const es = new EventSource(`${AGNES_API}/runs/${chatRes.run_id}/stream`)
        es.onmessage = (e) => {
          const ev = JSON.parse(e.data) as PipelineEvent
          events.push(ev)
          if (ev.node_id) {
            if (ev.event_type === 'node_started') updateNode(ev.node_id, { state: 'started' })
            if (ev.event_type === 'node_completed') updateNode(ev.node_id, { state: 'completed', elapsed: ev._elapsed_ms, output: ev.node_output })
            if (ev.event_type === 'node_failed') updateNode(ev.node_id, { state: 'failed', error: ev.error })
            if (ev.event_type === 'node_skipped') updateNode(ev.node_id, { state: 'skipped' })
          }
          if (ev.event_type === 'pipeline_completed' || ev.event_type === 'pipeline_failed' || ev.event_type === 'stream_closed') {
            es.close()
            resolve()
          }
        }
        es.onerror = () => { es.close(); resolve() }
      })

      const answer = extractAnswer(events)
      if (answer) {
        await speak(answer)
      } else {
        await speak('The pipeline completed. Check the data explorer for results.')
      }
    } catch (err) {
      console.error('Voice pipeline error:', err)
      setAgentState(null)
    }
  }, [speak, setActiveRun, updateNode])

  const startListening = useCallback(() => {
    type SpeechRecognitionCtor = { new(): {
      continuous: boolean; lang: string; start(): void; stop(): void;
      onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null;
      onerror: (() => void) | null;
      onend: (() => void) | null;
    }}
    const win = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor }
    const SpeechRec = win.SpeechRecognition ?? win.webkitSpeechRecognition
    if (!SpeechRec) {
      console.warn('Web Speech API not available')
      return
    }
    setAgentState('listening')
    const rec = new SpeechRec()
    rec.continuous = false
    rec.lang = 'en-US'
    rec.onresult = (e) => {
      const t = e.results[0][0].transcript
      inputVolRef.current = 0
      runPipeline(t)
    }
    rec.onerror = () => setAgentState(null)
    rec.onend = () => { if (agentState === 'listening') setAgentState(null) }
    rec.start()
  }, [runPipeline, agentState])

  return {
    agentState,
    lastPipeline,
    transcript,
    inputVolumeRef: inputVolRef,
    outputVolumeRef: outputVolRef,
    startListening,
  }
}
