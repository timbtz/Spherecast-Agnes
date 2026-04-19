import { Mic, MicOff, Send, Square, Volume2, X, FlaskConical, Package } from "lucide-react";
import { useState, useEffect } from "react";
import { useAgnesStore, type OrbState } from "@/store/agnesStore";
import { useAgnes } from "@/hooks/useAgnes";
import { isElevenLabsConfigured } from "@/lib/elevenlabs";
import { isSpeechRecognitionSupported } from "@/lib/speech";
import { VoiceOrb } from "@/components/orb/VoiceOrb";
import { cn } from "@/lib/utils";
import type { TabKey } from "@/components/layout/Sidebar";

const STATE_LABEL: Record<OrbState, string> = {
  idle: "Tap the orb to speak with Agnes",
  listening: "Listening…",
  thinking: "Thinking…",
  talking: "Speaking…",
  error: "Something went wrong",
};

export function OrbHero({ size = 220, onNavigateTo }: { size?: number; onNavigateTo?: (tab: TabKey) => void }) {
  const orbState = useAgnesStore((s) => s.orbState);
  const inputLevel = useAgnesStore((s) => s.inputLevel);
  const outputLevel = useAgnesStore((s) => s.outputLevel);
  const transcript = useAgnesStore((s) => s.transcript);
  const lastResponse = useAgnesStore((s) => s.lastResponse);

  const { startListening, stop, isActive, error, speak, sendText } = useAgnes();
  const [textInput, setTextInput] = useState("");
  const [responseDismissed, setResponseDismissed] = useState(false);

  // Reset dismiss state whenever a new response arrives
  useEffect(() => {
    if (lastResponse) setResponseDismissed(false);
  }, [lastResponse]);
  const sttSupported = isSpeechRecognitionSupported();
  const ttsConfigured = isElevenLabsConfigured();
  const isSecure = window.isSecureContext;

  const level = orbState === "talking" ? outputLevel : inputLevel;

  return (
    <div className="flex flex-col items-center text-center select-none">
      <button
        onClick={() => (isActive || orbState === "talking" ? stop() : startListening())}
        className="rounded-full bg-transparent border-0 p-0 outline-none focus:outline-none focus-visible:outline-none transition-transform active:scale-[0.98]"
        style={{ WebkitTapHighlightColor: "transparent", WebkitAppearance: "none" }}
        aria-label={orbState === "talking" ? "Stop speaking" : isActive ? "Stop listening" : "Start listening"}
      >
        <div className="relative">
          <VoiceOrb state={orbState} level={level} size={size} />
          {orbState === "talking" && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="rounded-full bg-white/75 backdrop-blur-sm p-3.5 shadow-md border border-border/40">
                <Square className="size-6 fill-foreground text-foreground" />
              </div>
            </div>
          )}
        </div>
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

      {lastResponse && !responseDismissed && orbState !== "thinking" && (
        <div className="mt-4 w-full max-w-xl rounded-xl border border-border bg-surface-subtle shadow-sm px-4 py-3 text-left animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
              <Volume2 className="size-3" /> Agnes
            </div>
            <button
              onClick={() => setResponseDismissed(true)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Dismiss response"
            >
              <X className="size-3.5" />
            </button>
          </div>
          <p className="text-[13.5px] text-foreground leading-relaxed whitespace-pre-wrap">{lastResponse}</p>
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            {ttsConfigured && (
              <button
                onClick={() => void speak(lastResponse)}
                className="text-[12px] text-primary hover:underline font-medium"
              >
                Read aloud again
              </button>
            )}
            {onNavigateTo && (
              <>
                <button
                  onClick={() => onNavigateTo("ingredients")}
                  className="inline-flex items-center gap-1 text-[11.5px] px-2 py-1 rounded-md border border-border bg-background hover:bg-accent/40 transition-colors text-foreground/80"
                >
                  <FlaskConical className="size-3" /> Ingredients
                </button>
                <button
                  onClick={() => onNavigateTo("suppliers")}
                  className="inline-flex items-center gap-1 text-[11.5px] px-2 py-1 rounded-md border border-border bg-background hover:bg-accent/40 transition-colors text-foreground/80"
                >
                  <Package className="size-3" /> Suppliers
                </button>
                <button
                  onClick={() => onNavigateTo("opportunities")}
                  className="inline-flex items-center gap-1 text-[11.5px] px-2 py-1 rounded-md border border-border bg-background hover:bg-accent/40 transition-colors text-foreground/80"
                >
                  View Opportunities
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {!isSecure && (
        <div className="mt-4 max-w-md text-[12px] text-status-failed bg-status-failed/8 border border-status-failed/20 rounded-md px-3 py-2">
          <MicOff className="size-3.5 inline -mt-0.5 mr-1" />
          Voice requires HTTPS. The app is running over HTTP — microphone access is blocked by the browser.
        </div>
      )}
      {isSecure && !sttSupported && (
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

      <form
        className="mt-5 flex w-full max-w-sm gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const t = textInput.trim();
          if (!t || isActive || orbState === "thinking" || orbState === "talking") return;
          setTextInput("");
          void sendText(t);
        }}
      >
        <input
          type="text"
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          placeholder="Or type a message…"
          disabled={isActive || orbState === "thinking" || orbState === "talking"}
          className="flex-1 rounded-lg border border-border bg-surface-subtle px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground/60 outline-none focus:border-primary/50 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!textInput.trim() || isActive || orbState === "thinking" || orbState === "talking"}
          className="rounded-lg border border-border bg-surface-subtle px-3 py-2 text-muted-foreground hover:text-foreground hover:border-primary/40 disabled:opacity-40 transition-colors"
          aria-label="Send"
        >
          <Send className="size-3.5" />
        </button>
      </form>
    </div>
  );
}
