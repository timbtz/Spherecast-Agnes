import { useState } from 'react'
import { useOpportunities } from '@/hooks/useData'
import { ConfidenceBar } from '@/components/ConfidenceBar'
import type { Opportunity } from '@/types/agnes'

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 5 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-slate-700 rounded animate-pulse" />
        </td>
      ))}
    </tr>
  )
}

function OpportunityRow({ opp, rank }: { opp: Opportunity; rank: number }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <>
      <tr
        className="border-b border-slate-700 hover:bg-slate-800 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3 text-slate-400 text-sm">{rank}</td>
        <td className="px-4 py-3 font-medium text-slate-100">{opp.ingredient}</td>
        <td className="px-4 py-3 text-center text-slate-300">{opp.company_count}</td>
        <td className="px-4 py-3"><ConfidenceBar value={opp.score} /></td>
        <td className="px-4 py-3">
          {opp.grade_flag ? (
            <span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">{opp.grade_flag}</span>
          ) : '—'}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-800/50">
          <td colSpan={5} className="px-6 py-4 text-sm text-slate-300">
            {opp.proposal_text ? (
              <p className="whitespace-pre-wrap">{opp.proposal_text}</p>
            ) : (
              <p className="text-slate-500 italic">
                No proposal generated yet — set ANTHROPIC_API_KEY and re-run Phase 4 to generate proposals.
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export function OpportunitiesTab() {
  const { data, isLoading, error } = useOpportunities()
  const [sortBy, setSortBy] = useState<'score' | 'company_count'>('score')

  const rows = [...(data?.opportunities ?? [])].sort((a, b) =>
    sortBy === 'score' ? b.score - a.score : b.company_count - a.company_count
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-100">
          Consolidation Opportunities
          {data && <span className="ml-2 text-sm font-normal text-slate-400">({data.count} total)</span>}
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setSortBy('score')}
            className={`px-3 py-1 text-xs rounded ${sortBy === 'score' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
          >Sort by Score</button>
          <button
            onClick={() => setSortBy('company_count')}
            className={`px-3 py-1 text-xs rounded ${sortBy === 'company_count' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
          >Sort by Companies</button>
        </div>
      </div>
      {error && <p className="text-red-400 text-sm">Failed to load opportunities</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-600 text-slate-400 text-left">
              <th className="px-4 py-2 font-medium">#</th>
              <th className="px-4 py-2 font-medium">Ingredient</th>
              <th className="px-4 py-2 font-medium text-center">Companies</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Grade</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : rows.map((opp, i) => <OpportunityRow key={opp.id} opp={opp} rank={i + 1} />)
            }
          </tbody>
        </table>
      </div>
    </div>
  )
}
