/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_ELEVENLABS_API_KEY: string
  readonly VITE_ELEVENLABS_VOICE_ID: string
  readonly VITE_AGNES_API_URL: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
