import { useCallback, useEffect, useRef, useState } from "react";
import { useAgnesStore, extractSpokenResponse } from "@/store/agnesStore";
import { agnesApi } from "@/lib/agnesApi";
import { isElevenLabsConfigured, speakWithElevenLabs } from "@/lib/elevenlabs";
import {
  isSpeechRecognitionSupported,
  startMicLevelMonitor,
  startSpeech,
} from "@/lib/speech";
import type { RunEvent } from "@/types/agnes";

// useAgnes — orchestrates: Web Speech (STT) → /chat → SSE stream → ElevenLabs TTS
export function useAgnes() {
  const {
    setOrbState,
    setInputLevel,
    setOutputLevel,
    setTranscript,
    setLastResponse,
    startRun,
    applyEvent,
    setGraph,
    activeRunId,
  } = useAgnesStore();

  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cleanupRef = useRef<Array<() => void>>([]);
  const eventsRef = useRef<RunEvent[]>([]);

  const cleanupAll = useCallback(() => {
    cleanupRef.current.forEach((fn) => { try { fn(); } catch { /* noop */ } });
    cleanupRef.current = [];
  }, []);

  // Speak a text snippet through ElevenLabs.
  const speak = useCallback(
    async (text: string) => {
      setLastResponse(text);
      if (!isElevenLabsConfigured()) {
        setOrbState("idle");
        return;
      }
      setOrbState("talking");
      const session = await speakWithElevenLabs(
        text,
        (lvl) => setOutputLevel(lvl),
        (s, msg) => {
          if (s === "error") {
            setError(msg ?? "TTS error");
            setOrbState("error");
            window.setTimeout(() => setOrbState("idle"), 1500);
          }
          if (s === "done") {
            setOutputLevel(0);
            setOrbState("idle");
          }
        },
      );
      if (session) {
        cleanupRef.current.push(session.stop);
        await session.done;
      }
    },
    [setLastResponse, setOrbState, setOutputLevel],
  );

  const handleTranscript = useCallback(
    async (text: string) => {
      setTranscript(text);
      setOrbState("thinking");
      try {
        const resp = await agnesApi.chat(text);
        let graph = null;
        try { graph = await agnesApi.pipelineGraph(resp.pipeline); } catch { /* noop */ }
        startRun(resp.run_id, resp.pipeline, graph);
        eventsRef.current = [];

        const closeStream = agnesApi.streamRun(
          resp.run_id,
          (ev) => {
            eventsRef.current.push(ev);
            applyEvent(ev);
            if (ev.event_type === "pipeline_completed" || ev.event_type === "pipeline_failed") {
              const spoken = extractSpokenResponse(eventsRef.current)
                ?? "Agnes finished the pipeline but produced no narrative response.";
              void speak(spoken);
            }
          },
          () => { /* stream closed */ },
        );
        cleanupRef.current.push(closeStream);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setOrbState("error");
        window.setTimeout(() => setOrbState("idle"), 1500);
      }
    },
    [applyEvent, setOrbState, setTranscript, speak, startRun],
  );

  const startListening = useCallback(async () => {
    if (isActive) return;
    setError(null);
    if (!isSpeechRecognitionSupported()) {
      setError("Voice input not supported in this browser. Use Chrome or Edge.");
      return;
    }
    setIsActive(true);
    setTranscript("");
    setOrbState("listening");

    const stopMic = await startMicLevelMonitor((v) => setInputLevel(v));
    cleanupRef.current.push(stopMic);

    const session = startSpeech({
      onInterim: (t) => setTranscript(t),
      onFinal: (t) => {
        setInputLevel(0);
        stopMic();
        void handleTranscript(t);
      },
      onError: (msg) => {
        setError(msg);
        setIsActive(false);
        setInputLevel(0);
        setOrbState("idle");
        stopMic();
      },
      onEnd: () => {
        setIsActive(false);
        setInputLevel(0);
      },
    });
    if (session) cleanupRef.current.push(session.stop);
  }, [handleTranscript, isActive, setInputLevel, setOrbState, setTranscript]);

  const stop = useCallback(() => {
    cleanupAll();
    setIsActive(false);
    setInputLevel(0);
    setOutputLevel(0);
    setOrbState("idle");
  }, [cleanupAll, setInputLevel, setOrbState, setOutputLevel]);

  useEffect(() => () => cleanupAll(), [cleanupAll]);

  return { startListening, stop, speak, isActive, error, activeRunId, setGraph };
}
