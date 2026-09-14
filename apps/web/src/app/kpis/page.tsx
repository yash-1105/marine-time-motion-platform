'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Types ────────────────────────────────────────────────────────────────────

interface ScorecardItem {
  kpi_number: number
  code: string
  name: string
  value?: number | null
  status: 'COMPUTED' | 'UNAVAILABLE' | 'NO_SOURCE_DATA'
  band?: 'GREEN' | 'AMBER' | 'RED' | 'GRAY'
  unit: string
  target?: number | null
  target_direction?: string
  thresholds?: { green?: number; amber?: number; red?: number }
  is_primary: boolean
  availability_status: string
  required_source_systems: string[]
}

interface ScorecardData {
  tenant_id: string
  total_kpis: number
  computed: number
  no_source_data: number
  unavailable: number
  include_aliases: boolean
  categories: Record<string, ScorecardItem[]>
}

interface KPITrendPoint {
  period: string
  value?: number | null
  band?: string
}

interface KPITrendData {
  kpi_code: string
  name: string
  status: string
  unit: string
  target?: number
  target_direction?: string
  direction: 'IMPROVING' | 'DETERIORATING' | 'STABLE'
  delta?: number | null
  percentage_change?: number | null
  rolling_average_3p?: number | null
  trend_points: KPITrendPoint[]
  notice?: string
}

interface KPIBenchmarkData {
  kpi_id: string
  kpi_code: string
  kpi_name: string
  has_benchmarks: boolean
  benchmarks: Array<{
    id: string
    peer_port: string
    benchmark_value: number
    source?: string
    period?: string
    notes?: string
  }>
  absent_notice?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function getBandColor(band?: string) {
  switch (band) {
    case 'GREEN':
      return 'bg-emerald-100 text-emerald-800 border-emerald-300'
    case 'AMBER':
      return 'bg-amber-100 text-amber-800 border-amber-300'
    case 'RED':
      return 'bg-rose-100 text-rose-800 border-rose-300'
    default:
      return 'bg-slate-100 text-slate-700 border-slate-300'
  }
}

function fmtValue(val?: number | null, unit?: string) {
  if (val === null || val === undefined) return '—'
  if (unit === '%' || unit === 'pct') return `${val.toFixed(2)}%`
  if (unit === 'hours' || unit === 'h') return `${val.toFixed(2)}h`
  if (unit === 'calls') return `${Math.round(val)} calls`
  if (unit === 'TEU') return `${Math.round(val).toLocaleString()} TEU`
  if (unit === 'moves/crane-hr') return `${val.toFixed(2)} moves/crane-hr`
  return `${val.toLocaleString()} ${unit || ''}`
}

export default function KPIDashboardPage() {
  const { token, can } = useAuth()
  const headers = { Authorization: `Bearer ${token || 'dev-token'}` }

  // State
  const [scorecard, setScorecard] = useState<ScorecardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('ALL')
  const [includeAliases, setIncludeAliases] = useState<boolean>(false)
  const [selectedKPI, setSelectedKPI] = useState<ScorecardItem | null>(null)
  const [kpiTrends, setKPITrends] = useState<KPITrendData | null>(null)
  const [kpiBenchmark, setKPIBenchmark] = useState<KPIBenchmarkData | null>(null)
  const [recalcModalOpen, setRecalcModalOpen] = useState(false)
  const [recalcReason, setRecalcReason] = useState('')
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Fetch Scorecard
  const fetchScorecard = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/v1/kpis/scorecard?include_aliases=${includeAliases}`, {
        headers: { Authorization: `Bearer ${token || 'dev-token'}` },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setScorecard(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setActionMessage({ type: 'error', text: `Failed to load KPI scorecard: ${msg}` })
    } finally {
      setLoading(false)
    }
  }, [includeAliases, token])

  useEffect(() => {
    fetchScorecard()
  }, [fetchScorecard])

  // Select KPI for detail drawer
  const handleSelectKPI = async (item: ScorecardItem) => {
    setSelectedKPI(item)
    try {
      const [trendRes, benchRes] = await Promise.all([
        fetch(`${API}/api/v1/kpis/${item.code}/trends`, { headers }),
        fetch(`${API}/api/v1/kpis/${item.code}/benchmark`, { headers }),
      ])
      if (trendRes.ok) setKPITrends(await trendRes.json())
      if (benchRes.ok) setKPIBenchmark(await benchRes.json())
    } catch {
      // Ignored
    }
  }

  // Execute Recalculation
  const handleRecalculate = async () => {
    if (!selectedKPI || !recalcReason.trim()) return
    try {
      const res = await fetch(`${API}/api/v1/kpis/${selectedKPI.code}/recalculate`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: recalcReason }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setActionMessage({ type: 'success', text: `Recalculated ${selectedKPI.code}. New value: ${data.value}. Audit event logged.` })
      setRecalcModalOpen(false)
      setRecalcReason('')
      fetchScorecard()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setActionMessage({ type: 'error', text: `Recalculation failed: ${msg}` })
    }
  }

  // Swap Primary/Alias
  const handleSwapPrimary = async (item: ScorecardItem) => {
    try {
      const res = await fetch(`${API}/api/v1/kpis/${item.code}/primary`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ make_primary: !item.is_primary }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setActionMessage({ type: 'success', text: `Updated primary/alias designation for ${item.code}.` })
      fetchScorecard()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setActionMessage({ type: 'error', text: `Failed to swap primary: ${msg}` })
    }
  }

  // Categories list
  const categoryNames = scorecard ? Object.keys(scorecard.categories) : []

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Governed KPI Engine & Scorecard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Complete catalogue of all 55 governed port operational KPIs (spec §11). Explicit status, lineage, and no fabricated values.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 bg-white px-3 py-1.5 rounded-md border border-slate-200 shadow-sm cursor-pointer">
            <input
              type="checkbox"
              checked={includeAliases}
              onChange={(e) => setIncludeAliases(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Show Alias Concepts (11/53, 14/51)
          </label>
          <button
            onClick={() => fetchScorecard()}
            className="text-xs font-semibold px-3 py-2 bg-slate-800 text-white rounded-md hover:bg-slate-700 transition"
          >
            Refresh Scorecard
          </button>
        </div>
      </div>

      {/* Banner / Feedback Message */}
      {actionMessage && (
        <div
          className={`p-3 rounded-md text-sm border flex justify-between items-center ${
            actionMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-rose-50 text-rose-800 border-rose-200'
          }`}
        >
          <span>{actionMessage.text}</span>
          <button onClick={() => setActionMessage(null)} className="font-bold ml-4">
            ×
          </button>
        </div>
      )}

      {/* High-level Governance Summary */}
      {scorecard && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Governed Registry</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{scorecard.total_kpis} KPIs</div>
            <div className="text-xs text-slate-400 mt-0.5">Exact spec numbering KPI-01 to KPI-55</div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Computed Population</div>
            <div className="text-2xl font-bold text-emerald-700 mt-1">{scorecard.computed} Active</div>
            <div className="text-xs text-emerald-600 mt-0.5">Evaluated against canonical records</div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">No Connected Source</div>
            <div className="text-2xl font-bold text-slate-700 mt-1">{scorecard.no_source_data} Registered</div>
            <div className="text-xs text-slate-400 mt-0.5">Yard/gate/maintenance (no fake zeroes)</div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
            <div className="text-xs font-semibold uppercase tracking-wider text-rose-600">Unavailable In Period</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{scorecard.unavailable} Missing</div>
            <div className="text-xs text-slate-400 mt-0.5">Missing inputs named explicitly</div>
          </div>
        </div>
      )}

      {/* Category Tabs */}
      <div className="flex border-b border-slate-200 overflow-x-auto gap-1 text-sm font-medium">
        <button
          onClick={() => setActiveTab('ALL')}
          className={`py-2 px-3 border-b-2 whitespace-nowrap ${
            activeTab === 'ALL'
              ? 'border-blue-600 text-blue-600 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          All Categories
        </button>
        {categoryNames.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveTab(cat)}
            className={`py-2 px-3 border-b-2 whitespace-nowrap ${
              activeTab === cat
                ? 'border-blue-600 text-blue-600 font-semibold'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            {cat} ({scorecard?.categories[cat].length || 0})
          </button>
        ))}
      </div>

      {/* KPI Cards / Tables */}
      {loading ? (
        <div className="p-12 text-center text-slate-500">Loading governed KPI metrics...</div>
      ) : scorecard ? (
        <div className="space-y-6">
          {categoryNames
            .filter((cat) => activeTab === 'ALL' || activeTab === cat)
            .map((cat) => {
              const items = scorecard.categories[cat]
              return (
                <div key={cat} className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                  <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-200 flex justify-between items-center">
                    <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">{cat}</h2>
                    <span className="text-xs font-medium text-slate-500">{items.length} metrics</span>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {items.map((item) => (
                      <div
                        key={item.code}
                        className="px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/70 transition"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                              {item.code}
                            </span>
                            <span className="text-sm font-semibold text-slate-900">{item.name}</span>
                            {!item.is_primary && (
                              <button
                                onClick={() => handleSwapPrimary(item)}
                                title="Click to designate as primary"
                                className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition"
                              >
                                Alias (Make Primary)
                              </button>
                            )}
                          </div>
                          <div className="text-xs text-slate-500">
                            Unit: <span className="font-medium text-slate-700">{item.unit}</span>
                            {item.target !== undefined && item.target !== null && (
                              <span className="ml-3">
                                Target: <span className="font-medium text-slate-700">{item.target}</span> (
                                {item.target_direction === 'HIGHER_IS_BETTER' ? 'Higher is better' : 'Lower is better'})
                              </span>
                            )}
                          </div>
                          {item.status === 'NO_SOURCE_DATA' && (
                            <div className="text-xs text-slate-500 italic">
                              Requires: {item.required_source_systems.join(', ') || 'Connected sensors/gate systems'}
                            </div>
                          )}
                        </div>

                        <div className="flex items-center gap-4 self-start sm:self-center">
                          {item.status === 'COMPUTED' ? (
                            <div className="text-right">
                              <div className="text-base font-bold text-slate-900">{fmtValue(item.value, item.unit)}</div>
                              <span className={`inline-block text-[11px] font-bold px-2 py-0.5 rounded-full border ${getBandColor(item.band)}`}>
                                {item.band || 'BAND UNSET'}
                              </span>
                            </div>
                          ) : item.status === 'NO_SOURCE_DATA' ? (
                            <div className="text-right">
                              <span className="text-xs font-medium px-2.5 py-1 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                NO SOURCE DATA
                              </span>
                            </div>
                          ) : (
                            <div className="text-right">
                              <span className="text-xs font-medium px-2.5 py-1 rounded bg-rose-50 text-rose-700 border border-rose-200">
                                UNAVAILABLE
                              </span>
                            </div>
                          )}

                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleSelectKPI(item)}
                              className="text-xs font-medium px-2.5 py-1.5 text-blue-600 hover:text-blue-800 bg-blue-50/50 hover:bg-blue-100/50 rounded transition"
                            >
                              Lineage & Trends
                            </button>
                            {item.status === 'COMPUTED' && can('recalculate') && (
                              <button
                                onClick={() => {
                                  setSelectedKPI(item)
                                  setRecalcModalOpen(true)
                                }}
                                className="text-xs font-medium px-2.5 py-1.5 text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded transition"
                              >
                                Recalculate
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
        </div>
      ) : null}

      {/* Recalculate Modal */}
      {recalcModalOpen && selectedKPI && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-6 shadow-xl space-y-4 border border-slate-200">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Permissioned Recalculation</h3>
              <p className="text-xs text-slate-500 mt-1">
                Recalculating {selectedKPI.code} ({selectedKPI.name}). An entry will be permanently logged in audit.audit_event.
              </p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                Audit Reason / Justification <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={recalcReason}
                onChange={(e) => setRecalcReason(e.target.value)}
                placeholder="e.g. Verified data correction or periodic governance recalculation"
                rows={3}
                className="w-full text-xs p-2.5 border border-slate-300 rounded focus:ring-1 focus:ring-blue-500 outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setRecalcModalOpen(false)}
                className="text-xs px-3 py-1.5 text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleRecalculate}
                disabled={!recalcReason.trim()}
                className="text-xs font-semibold px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded transition"
              >
                Execute Recalculation
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detail & Trends Drawer */}
      {selectedKPI && (
        <div className="bg-slate-50 rounded-lg border border-slate-300 p-5 space-y-4 shadow-sm">
          <div className="flex justify-between items-start border-b border-slate-200 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-blue-700">{selectedKPI.code}</span>
                <h3 className="text-base font-bold text-slate-900">{selectedKPI.name}</h3>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Unit: {selectedKPI.unit}</p>
            </div>
            <button
              onClick={() => {
                setSelectedKPI(null)
                setKPITrends(null)
                setKPIBenchmark(null)
              }}
              className="text-sm font-bold text-slate-400 hover:text-slate-600"
            >
              ✕ Close
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Trends */}
            <div className="bg-white p-4 rounded border border-slate-200 space-y-2">
              <div className="flex justify-between items-center">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">Trend & Direction</h4>
                {kpiTrends && (
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      kpiTrends.direction === 'IMPROVING'
                        ? 'bg-emerald-100 text-emerald-800'
                        : kpiTrends.direction === 'DETERIORATING'
                        ? 'bg-rose-100 text-rose-800'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {kpiTrends.direction}
                  </span>
                )}
              </div>
              {kpiTrends ? (
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between text-slate-600">
                    <span>Rolling 3-Period Average:</span>
                    <span className="font-semibold">{fmtValue(kpiTrends.rolling_average_3p, selectedKPI.unit)}</span>
                  </div>
                  {kpiTrends.delta !== null && (
                    <div className="flex justify-between text-slate-600">
                      <span>Prior Period Delta:</span>
                      <span className="font-semibold">
                        {kpiTrends.delta && kpiTrends.delta > 0 ? `+${kpiTrends.delta}` : kpiTrends.delta}{' '}
                        {kpiTrends.percentage_change ? `(${kpiTrends.percentage_change}%)` : ''}
                      </span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-slate-100 space-y-1">
                    <div className="font-semibold text-slate-500 text-[11px] uppercase">Recent Periods:</div>
                    {kpiTrends.trend_points.map((tp, idx) => (
                      <div key={idx} className="flex justify-between text-slate-700">
                        <span>{tp.period}</span>
                        <span className="font-mono font-medium">{fmtValue(tp.value, selectedKPI.unit)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-xs text-slate-400">Loading trend points...</div>
              )}
            </div>

            {/* Peer Port Benchmark */}
            <div className="bg-white p-4 rounded border border-slate-200 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">Peer Port Benchmarks</h4>
              {kpiBenchmark ? (
                kpiBenchmark.has_benchmarks ? (
                  <div className="space-y-2 text-xs">
                    {kpiBenchmark.benchmarks.map((b) => (
                      <div key={b.id} className="p-2 bg-slate-50 rounded border border-slate-200 space-y-1">
                        <div className="flex justify-between font-semibold text-slate-900">
                          <span>{b.peer_port}</span>
                          <span>{fmtValue(b.benchmark_value, selectedKPI.unit)}</span>
                        </div>
                        <div className="text-[11px] text-slate-500">
                          Source: {b.source || '—'} | Period: {b.period || '—'}
                        </div>
                        {b.notes && <div className="text-[11px] text-slate-600">{b.notes}</div>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 space-y-1">
                    <p className="font-medium text-slate-700">No peer-port benchmark data configured.</p>
                    <p className="text-slate-500">{kpiBenchmark.absent_notice}</p>
                  </div>
                )
              ) : (
                <div className="text-xs text-slate-400">Checking benchmarks...</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
