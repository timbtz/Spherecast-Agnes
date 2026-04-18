// Custom ElevenLabs streaming TTS client.
// Posts text to /v1/text-to-speech/{voiceId}/stream, decodes the MP3 response
// via the Web Audio API, and feeds frequency data back for orb animation.

const API_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY as string | undefined;
const VOICE_ID =
  (import.meta.env.VITE_ELEVENLABS_VOICE_ID as string | undefined) ??
  "EXAVITQu4vr4xnSDxMaL"; // Sarah by default

export function isElevenLabsConfigured(): boolean {
  return Boolean(API_KEY && API_KEY.length > 8);
}

export interface SpeakSession {
  stop: () => void;
  done: Promise<void>;
}

export async function speakWithElevenLabs(
  text: string,
  onLevel: (v: number) => void,
  onState: (s: "loading" | "speaking" | "done" | "error", msg?: string) => void,
): Promise<SpeakSession | null> {
  if (!API_KEY) {
    onState("error", "VITE_ELEVENLABS_API_KEY not configured");
    return null;
  }
  onState("loading");

  let audioCtx: AudioContext | null = null;
  let source: AudioBufferSourceNode | null = null;
  let analyser: AnalyserNode | null = null;
  let raf = 0;
  let stopped = false;

  const done = (async () => {
    try {
      const res = await fetch(
        `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream?output_format=mp3_44100_128`,
        {
          method: "POST",
          headers: {
            "xi-api-key": API_KEY,
            "Content-Type": "application/json",
            Accept: "audio/mpeg",
          },
          body: JSON.stringify({
            text,
            model_id: "eleven_turbo_v2_5",
            voice_settings: {
              stability: 0.5,
              similarity_boost: 0.75,
              style: 0.3,
              use_speaker_boost: true,
              speed: 1.0,
            },
          }),
        },
      );
      if (!res.ok) {
        const errBody = await res.text().catch(() => "");
        throw new Error(`ElevenLabs ${res.status}: ${errBody.slice(0, 120)}`);
      }
      const buf = await res.arrayBuffer();
      if (stopped) return;
      audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      const decoded = await audioCtx.decodeAudioData(buf.slice(0));
      if (stopped) return;
      source = audioCtx.createBufferSource();
      source.buffer = decoded;
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        if (!analyser) return;
        analyser.getByteFrequencyData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i];
        onLevel(Math.min(1, (sum / data.length / 255) * 2));
        raf = requestAnimationFrame(tick);
      };
      onState("speaking");
      tick();
      await new Promise<void>((resolve) => {
        source!.onended = () => resolve();
        source!.start();
      });
      onLevel(0);
      onState("done");
    } catch (err) {
      onState("error", err instanceof Error ? err.message : String(err));
    } finally {
      cancelAnimationFrame(raf);
      try { source?.stop(); } catch { /* noop */ }
      void audioCtx?.close();
    }
  })();

  return {
    stop: () => {
      stopped = true;
      try { source?.stop(); } catch { /* noop */ }
      cancelAnimationFrame(raf);
      void audioCtx?.close();
      onLevel(0);
    },
    done,
  };
}
