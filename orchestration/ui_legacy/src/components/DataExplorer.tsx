import { useState } from 'react'
import { OpportunitiesTab } from '@/components/tabs/OpportunitiesTab'
import { IngredientsTab } from '@/components/tabs/IngredientsTab'
import { ComplianceTab } from '@/components/tabs/ComplianceTab'
import { ProposalsTab } from '@/components/tabs/ProposalsTab'
import { RunsTab } from '@/components/tabs/RunsTab'
import { useRunStore } from '@/store/runStore'
import type { PipelineRun } from '@/types/agnes'

const TABS = [
  { id: 'opportunities', label: 'Opportunities' },
  { id: 'ingredients', label: 'Ingredients' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'proposals', label: 'Proposals' },
  { id: 'runs', label: 'Runs' },
]

export function DataExplorer({ onSpeak }: { onSpeak?: (text: string) => void }) {
  const [active, setActive] = useState('opportunities')
  const { setActiveRun } = useRunStore()

  function handleSelectRun(run: PipelineRun) {
    setActiveRun(run.id, run.pipeline_name)
    setActive('runs')
  }

  return (
    <div>
      <div className="flex gap-1 mb-6 border-b border-slate-700">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              active === tab.id
                ? 'border-blue-400 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div>
        {active === 'opportunities' && <OpportunitiesTab />}
        {active === 'ingredients' && <IngredientsTab />}
        {active === 'compliance' && <ComplianceTab />}
        {active === 'proposals' && <ProposalsTab onSpeak={onSpeak} />}
        {active === 'runs' && <RunsTab onSelectRun={handleSelectRun} />}
      </div>
    </div>
  )
}
