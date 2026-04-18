import { useState } from 'react'
import { useIngredients } from '@/hooks/useData'
import type { Ingredient } from '@/types/agnes'

const GRADE_OPTIONS = ['', 'supplement', 'food', 'excipient', 'sweetener', 'flavor', 'unknown']

function SlideOver({ ingredient, onClose }: { ingredient: Ingredient; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="w-96 bg-slate-900 border-l border-slate-700 h-full overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-100">{ingredient.display_name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl">✕</button>
        </div>
        <div className="space-y-3 text-sm">
          <div><span className="text-slate-400">UNII:</span> <span className="text-slate-200 ml-2">{ingredient.unii_code ?? 'N/A'}</span></div>
          <div><span className="text-slate-400">CAS:</span> <span className="text-slate-200 ml-2">{ingredient.cas_number ?? 'N/A'}</span></div>
          <div><span className="text-slate-400">PubChem CID:</span> <span className="text-slate-200 ml-2">{ingredient.pubchem_cid ?? 'N/A'}</span></div>
          <div><span className="text-slate-400">Grade:</span> <span className="text-slate-200 ml-2">{ingredient.grade_flag ?? 'unknown'}</span></div>
          <div><span className="text-slate-400">Substitution edges:</span> <span className="text-slate-200 ml-2">{ingredient.substitution_edges}</span></div>
          <div>
            <span className="text-slate-400">SMILES:</span>
            <pre className="mt-1 text-xs text-green-400 bg-slate-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">
              {ingredient.smiles ?? 'N/A'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 5 }).map((_, i) => (
        <td key={i} className="px-4 py-3"><div className="h-4 bg-slate-700 rounded animate-pulse" /></td>
      ))}
    </tr>
  )
}

export function IngredientsTab() {
  const [grade, setGrade] = useState('')
  const [selected, setSelected] = useState<Ingredient | null>(null)
  const { data, isLoading, error } = useIngredients(grade || undefined)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-100">
          Ingredients
          {data && <span className="ml-2 text-sm font-normal text-slate-400">({data.ingredients.length})</span>}
        </h2>
        <select
          value={grade}
          onChange={e => setGrade(e.target.value)}
          className="bg-slate-700 border border-slate-600 text-slate-300 text-sm rounded px-2 py-1"
        >
          {GRADE_OPTIONS.map(g => (
            <option key={g} value={g}>{g || 'All grades'}</option>
          ))}
        </select>
      </div>
      {error && <p className="text-red-400 text-sm">Failed to load ingredients</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-600 text-slate-400 text-left">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">UNII</th>
              <th className="px-4 py-2 font-medium">Grade</th>
              <th className="px-4 py-2 font-medium">SMILES</th>
              <th className="px-4 py-2 font-medium text-center">Subs</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : data?.ingredients.map(ing => (
                <tr
                  key={ing.id}
                  className="border-b border-slate-700 hover:bg-slate-800 cursor-pointer"
                  onClick={() => setSelected(ing)}
                >
                  <td className="px-4 py-3 text-slate-100 font-medium">{ing.display_name}</td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs">{ing.unii_code ?? '—'}</td>
                  <td className="px-4 py-3">
                    {ing.grade_flag ? (
                      <span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">{ing.grade_flag}</span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-green-400">
                    {ing.smiles ? ing.smiles.slice(0, 20) + (ing.smiles.length > 20 ? '…' : '') : '—'}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-400">{ing.substitution_edges}</td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>
      {selected && <SlideOver ingredient={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
