import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { VoiceOrb } from '@/components/VoiceOrb'
import { DagPanel } from '@/components/DagPanel'
import { DataExplorer } from '@/components/DataExplorer'
import { useHealth } from '@/hooks/useData'

const qc = new QueryClient()

function Header() {
  const { data } = useHealth()
  const ok = data?.status === 'ok'
  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-slate-700 bg-slate-900 flex-shrink-0">
      <h1 className="font-mono text-lg font-semibold text-slate-100 tracking-wider">SPHERECAST · Agnes</h1>
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span className={`text-base ${ok ? 'text-green-400' : 'text-red-400'}`}>●</span>
        {ok ? 'API Online' : 'API Offline'}
      </div>
    </header>
  )
}

function Inner() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-100 flex flex-col">
      <Header />
      <main className="flex flex-1 overflow-hidden min-h-0">
        <aside className="w-72 flex-shrink-0 flex flex-col items-center gap-6 p-6 border-r border-slate-700 overflow-y-auto">
          <VoiceOrb />
          <div className="w-full">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">Pipeline Monitor</div>
            <DagPanel />
          </div>
        </aside>
        <section className="flex-1 overflow-auto p-6">
          <DataExplorer />
        </section>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <Inner />
    </QueryClientProvider>
  )
}
