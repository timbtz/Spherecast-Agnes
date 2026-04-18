import { useProposals } from '@/hooks/useData'
import { ConfidenceBar } from '@/components/ConfidenceBar'
import type { Proposal } from '@/types/agnes'

function ProposalCard({ proposal, onSpeak }: { proposal: Proposal; onSpeak?: (text: string) => void }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-semibold text-slate-100">{proposal.ingredient}</h3>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-slate-400">{proposal.company_count} companies</span>
            <ConfidenceBar value={proposal.score} />
          </div>
        </div>
        {onSpeak && (
          <button
            onClick={() => onSpeak(proposal.proposal_text)}
            className="text-xs bg-blue-700 hover:bg-blue-600 text-white px-3 py-1 rounded"
          >
            Speak this
          </button>
        )}
      </div>
      <p className="text-sm text-slate-300 mt-3 whitespace-pre-wrap leading-relaxed">{proposal.proposal_text}</p>
    </div>
  )
}

export function ProposalsTab({ onSpeak }: { onSpeak?: (text: string) => void }) {
  const { data, isLoading, error } = useProposals()

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 bg-slate-700 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) return <p className="text-red-400 text-sm">Failed to load proposals</p>

  if (!data || data.proposals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="text-4xl mb-4">📋</div>
        <h3 className="text-lg font-semibold text-slate-300 mb-2">No proposals generated yet</h3>
        <p className="text-sm text-slate-500 max-w-sm">
          Set <code className="bg-slate-800 px-1 rounded">ANTHROPIC_API_KEY</code> and re-run Phase 4 to generate AI-powered consolidation proposals.
        </p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-100 mb-4">
        Proposals <span className="text-sm font-normal text-slate-400">({data.proposals.length})</span>
      </h2>
      <div className="space-y-4">
        {data.proposals.map((p, i) => <ProposalCard key={i} proposal={p} onSpeak={onSpeak} />)}
      </div>
    </div>
  )
}
