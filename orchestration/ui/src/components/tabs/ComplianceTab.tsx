import { useState, useMemo } from 'react'
import { useCompliance } from '@/hooks/useData'
import type { ComplianceRow } from '@/types/agnes'

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 5 }).map((_, i) => (
        <td key={i} className="px-3 py-2"><div className="h-4 bg-slate-700 rounded animate-pulse" /></td>
      ))}
    </tr>
  )
}

export function ComplianceTab() {
  const { data, isLoading, error } = useCompliance()
  const [filterCert, setFilterCert] = useState('')

  const allCerts = useMemo(() => {
    if (!data) return [] as string[]
    return [...new Set(data.compliance.map((r: ComplianceRow) => r.cert_type))].sort()
  }, [data])

  const productCertMap = useMemo(() => {
    if (!data) return new Map<string, Set<string>>()
    const map = new Map<string, Set<string>>()
    for (const row of data.compliance as ComplianceRow[]) {
      const key = `${row.product_id}|${row.company}`
      if (!map.has(key)) map.set(key, new Set())
      if (row.status === 'certified' || row.status === 'implied') {
        map.get(key)!.add(row.cert_type)
      }
    }
    return map
  }, [data])

  const visibleCerts = filterCert ? [filterCert] : allCerts.slice(0, 6)

  const products = useMemo(() => {
    return [...new Set((data?.compliance as ComplianceRow[] | undefined)?.map((r: ComplianceRow) => `${r.product_id}|${r.company}`) ?? [])]
      .sort((a: string, b: string) => a.split('|')[1].localeCompare(b.split('|')[1]))
  }, [data])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-100">
          Compliance
          {data && <span className="ml-2 text-sm font-normal text-slate-400">({products.length} products)</span>}
        </h2>
        <select
          value={filterCert}
          onChange={e => setFilterCert(e.target.value)}
          className="bg-slate-700 border border-slate-600 text-slate-300 text-sm rounded px-2 py-1"
        >
          <option value="">All cert types</option>
          {allCerts.map((c: string) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      {error && <p className="text-red-400 text-sm">Failed to load compliance data</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-600 text-slate-400 text-left">
              <th className="px-3 py-2 font-medium">Company</th>
              {visibleCerts.map((c: string) => <th key={c} className="px-3 py-2 font-medium text-center text-xs">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
              : products.map((key: string) => {
                const [, company] = key.split('|')
                const certs = productCertMap.get(key) ?? new Set<string>()
                return (
                  <tr key={key} className="border-b border-slate-700 hover:bg-slate-800">
                    <td className="px-3 py-2 text-slate-200 font-medium text-xs">{company}</td>
                    {visibleCerts.map((c: string) => (
                      <td key={c} className="px-3 py-2 text-center">
                        {certs.has(c)
                          ? <span className="text-green-400 font-bold">✓</span>
                          : <span className="text-slate-700">—</span>
                        }
                      </td>
                    ))}
                  </tr>
                )
              })
            }
          </tbody>
        </table>
      </div>
    </div>
  )
}
