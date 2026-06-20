// Tiny wrapper around the browser SpeechRecognition API.
// Returns final transcript via onResult. No-op if unsupported.

type SR = typeof window extends { SpeechRecognition: infer T } ? T : unknown;

interface MinimalSR {
  start: () => void;
  stop: () => void;
  abort: () => void;
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((ev: { results: { isFinal: boolean; 0: { transcript: string } }[]; resultIndex: number }) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

function getCtor(): { new (): MinimalSR } | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition as { new (): MinimalSR } | undefined)
    ?? (w.webkitSpeechRecognition as { new (): MinimalSR } | undefined)
    ?? null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getCtor() !== null;
}

export interface SpeechSession {
  stop: () => void;
}

export function startSpeech(opts: {
  onInterim?: (t: string) => void;
  onFinal: (t: string) => void;
  onError?: (msg: string) => void;
  onEnd?: () => void;
  onStart?: () => void;
  lang?: string;
}): SpeechSession | null {
  const Ctor = getCtor();
  if (!Ctor) {
    opts.onError?.("Speech recognition not supported in this browser. Try Chrome or Edge.");
    return null;
  }
  const rec = new Ctor();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = opts.lang ?? "en-US";
  let finalText = "";
  rec.onstart = () => opts.onStart?.();
  rec.onresult = (ev) => {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const res = ev.results[i];
      const txt = res[0].transcript;
      if (res.isFinal) finalText += txt;
      else interim += txt;
    }
    if (interim) opts.onInterim?.(interim);
  };
  const ERROR_LABELS: Record<string, string> = {
    "not-allowed": "Microphone access denied. Allow mic in browser settings, or access the app via HTTPS.",
    "service-not-allowed": "Speech recognition is not permitted on this origin (requires HTTPS).",
    "no-speech": "No speech detected — try speaking closer to your microphone.",
    "audio-capture": "No microphone found. Check that a mic is connected.",
    "network": "Network error during speech recognition. Check your connection.",
    "aborted": "Speech recognition was aborted.",
    "bad-grammar": "Speech grammar error.",
    "language-not-supported": "Language not supported by speech recognition.",
  };
  rec.onerror = (ev) => opts.onError?.(ERROR_LABELS[ev.error ?? ""] ?? ev.error ?? "speech error");
  rec.onend = () => {
    if (finalText.trim()) opts.onFinal(finalText.trim());
    opts.onEnd?.();
  };
  try {
    rec.start();
  } catch (e) {
    opts.onError?.(String(e));
    return null;
  }
  return { stop: () => { try { rec.stop(); } catch { /* noop */ } } };
}

// ---------------------------------------------------------------------------
// Mic level monitor — runs an AnalyserNode while recording for orb input volume.
// ---------------------------------------------------------------------------
export async function startMicLevelMonitor(onLevel: (v: number) => void): Promise<() => void> {
  let stream: MediaStream | null = null;
  let ctx: AudioContext | null = null;
  let raf = 0;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      const avg = sum / data.length / 255;
      onLevel(Math.min(1, avg * 2));
      raf = requestAnimationFrame(tick);
    };
    tick();
  } catch (e) {
    onLevel(0);
  }
  return () => {
    cancelAnimationFrame(raf);
    stream?.getTracks().forEach((t) => t.stop());
    void ctx?.close();
  };
}
