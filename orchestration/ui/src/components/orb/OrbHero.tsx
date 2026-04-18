import { Mic, MicOff, Square, Volume2 } from "lucide-react";
import { useAgnesStore, type OrbState } from "@/store/agnesStore";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { isSpeechRecognitionSupported } from "@/lib/speech";
import { VoiceOrb } from "@/components/orb/VoiceOrb";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<OrbState, string> = {
  idle: "Tap the orb to speak with Agnes",
  listening: "Listening…",
  thinking: "Thinking…",
  talking: "Speaking…",
  error: "Something went wrong",
};

export function OrbHero({ size = 220 }: { size?: number }) {
  const orbState = useAgnesStore((s) => s.orbState);
  const inputLevel = useAgnesStore((s) => s.inputLevel);
  const outputLevel = useAgnesStore((s) => s.outputLevel);
  const transcript = useAgnesStore((s) => s.transcript);
  const lastResponse = useAgnesStore((s) => s.lastResponse);

  const { startListening, stop, isActive, error, speak } = useAgnes();
  const sttSupported = isSpeechRecognitionSupported();
  const ttsConfigured = isElevenLabsConfigured();

  const level = orbState === "talking" ? outputLevel : inputLevel;

  return (
    <div className="flex flex-col items-center text-center select-none">
      <button
        onClick={() => (isActive || orbState === "talking" ? stop() : startListening())}
        className="rounded-full bg-transparent border-0 p-0 outline-none focus:outline-none focus-visible:outline-none transition-transform active:scale-[0.98]"
        style={{ WebkitTapHighlightColor: "transparent", WebkitAppearance: "none" }}
        aria-label={isActive ? "Stop listening" : "Start listening"}
      >
        <VoiceOrb state={orbState} level={level} size={size} />
      </button>

      <div className="mt-5 flex items-center gap-2">
        <span className={cn(
          "size-1.5 rounded-full",
          orbState === "idle" && "bg-muted-foreground/40",
          orbState === "listening" && "bg-orb-listening animate-status-pulse",
          orbState === "thinking" && "bg-orb-thinking animate-status-pulse",
          orbState === "talking" && "bg-orb-talking animate-status-pulse",
          orbState === "error" && "bg-status-failed",
        )} />
        <p className="text-[13px] text-muted-foreground font-medium">{STATE_LABEL[orbState]}</p>
      </div>

      {transcript && (
        <p className="mt-3 max-w-md text-[14px] text-foreground italic leading-snug animate-fade-in">
          "{transcript}"
        </p>
      )}

      {lastResponse && orbState !== "thinking" && (
        <div className="mt-4 max-w-lg rounded-lg border border-border bg-surface-subtle px-4 py-3 text-left animate-fade-in">
          <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5 font-semibold">
            <Volume2 className="size-3" /> Agnes
          </div>
          <p className="text-[13.5px] text-foreground leading-relaxed line-clamp-6">{lastResponse}</p>
          {ttsConfigured && (
            <button
              onClick={() => void speak(lastResponse)}
              className="mt-2 text-[12px] text-primary hover:underline font-medium"
            >
              Read aloud again
            </button>
          )}
        </div>
      )}

      {!sttSupported && (
        <div className="mt-4 max-w-md text-[12px] text-status-failed bg-status-failed/8 border border-status-failed/20 rounded-md px-3 py-2">
          <MicOff className="size-3.5 inline -mt-0.5 mr-1" />
          Voice input not supported in this browser. Try Chrome or Edge.
        </div>
      )}
      {!ttsConfigured && sttSupported && (
        <div className="mt-3 max-w-md text-[11.5px] text-muted-foreground">
          <span className="font-mono">VITE_ELEVENLABS_API_KEY</span> not configured — orb will animate but Agnes will not speak.
        </div>
      )}
      {error && (
        <p className="mt-2 text-[12px] text-status-failed">{error}</p>
      )}
    </div>
  );
}
