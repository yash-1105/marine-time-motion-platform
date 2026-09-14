'use client'

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth-context'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Types ────────────────────────────────────────────────────────────────────

interface LeadTimeDef {
  id: string
  name: string
  start_event: string
  end_event: string
  description?: string
  formula_version: string
  unit: string
  null_handling: string
  occurrence_selection: string
  availability_status: 'COMPUTABLE' | 'NO_SOURCE_DATA'
  required_events?: string[]
  is_execution_delay: boolean
  execution_delay_movement?: string
  custom_builder: boolean
}

interface MetricStat {
  definition_id: string
  definition_name: string
  cohort_key: string
  observation_count: number
  missing_count: number
  mean_hours?: number
  median_hours?: number
  std_hours?: number
  cv?: number
  min_hours?: number
  max_hours?: number
  p25_hours?: number
  p75_hours?: number
  p90_hours?: number
  p95_hours?: number
  fastest_vcn?: string
  slowest_vcn?: string
  tail_risk_ratio?: number
  right_skew_flag?: boolean
  percentile_method: string
  small_sample_warning: boolean
  outlier_vcns?: string[]
  formula_version?: string
  quarantine_excluded: boolean
  calculated_at?: string
}

interface PerCallResult {
  id: string
  vessel_call_id: string
  vcn: string
  vessel_name?: string
  duration_hours?: number
  status: string
  unavailable_reason?: string
  start_time?: string
  end_time?: string
  traceability: {
    formula_version?: string
    source_record_ids: string[]
    filter_context: Record<string, unknown>
    exclusions_applied: string[]
    dq_status?: string
    calculated_at?: string
  }
}

interface ReconciliationMetric {
  definition_name: string
  expected_metric: string
  total_eligible_calls: number
  passed: number
  failed: number
  unavailable_in_actual: number
  reconciled_fraction: string
  details: Array<{
    vcn: string
    status: string
    actual?: number
    expected?: number
    diff?: number
    reason?: string
  }>
}

interface ReconciliationReport {
  tolerance_hours: number
  overall_status: string
  summary: {
    total_targets: number
    fully_reconciled_targets: number
    total_comparisons: number
    passed_comparisons: number
    failed_comparisons: number
  }
  early_service: {
    negative_arrival_delays: number
    negative_sailing_delays: number
  }
  metrics_reconciled: Record<string, ReconciliationMetric>
}

interface EventDef {
  id: string
  name: string
  category?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtHours(h: number | null | undefined): string {
  if (h == null) return '—'
  const sign = h < 0 ? '-' : ''
  const abs = Math.abs(h)
  const hh = Math.floor(abs)
  const mm = Math.round((abs - hh) * 60)
  return `${sign}${hh}h ${mm}m (${h >= 0 ? '+' : ''}${h.toFixed(2)}h)`
}

function fmtTs(ts?: string | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', hour12: false })
  } catch {
    return ts
  }
}

// ── Main Page ────────────────────────────────────────────────────────────────

function TimeAndMotionContent() {
  const { token, can } = useAuth()
  const headers = { Authorization: `Bearer ${token || 'dev-token'}` }

  const [activeTab, setActiveTab] = useState<'catalogue' | 'reconciliation' | 'explorer' | 'custom'>('catalogue')

  // Data states
  const [definitions, setDefinitions] = useState<LeadTimeDef[]>([])
  const [statsMap, setStatsMap] = useState<Record<string, MetricStat>>({})
  const [loadingDefs, setLoadingDefs] = useState(true)
  const [recomputing, setRecomputing] = useState(false)
  const [computeMsg, setComputeMsg] = useState<string | null>(null)

  // Reconciliation state
  const [reconciliation, setReconciliation] = useState<ReconciliationReport | null>(null)
  const [loadingRecon, setLoadingRecon] = useState(false)

  // Explorer state
  const [selectedDefId, setSelectedDefId] = useState<string>('')
  const [results, setResults] = useState<PerCallResult[]>([])
  const [resultsTotal, setResultsTotal] = useState(0)
  const [loadingResults, setLoadingResults] = useState(false)
  const [selectedResult, setSelectedResult] = useState<PerCallResult | null>(null)

  // Custom Builder state
  const searchParams = useSearchParams()
  const globalVesselType = searchParams.get('vesselType') || ''
  const globalCargoType = searchParams.get('cargoType') || ''
  const [customVesselType, setCustomVesselType] = useState(globalVesselType)
  const [customCargoType, setCustomCargoType] = useState(globalCargoType)

  useEffect(() => {
    if (globalVesselType) setCustomVesselType(globalVesselType)
    if (globalCargoType) setCustomCargoType(globalCargoType)
  }, [globalVesselType, globalCargoType])

  const [events, setEvents] = useState<EventDef[]>([])
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [customOcc, setCustomOcc] = useState('first')
  const [customScope, setCustomScope] = useState('')
  const [customSaveName, setCustomSaveName] = useState('')
  const [customRunning, setCustomRunning] = useState(false)
  const [customOutput, setCustomOutput] = useState<{
    formula?: string
    aggregate?: {
      observation_count?: number
      missing_count?: number
      mean_hours?: number
      median_hours?: number
      p90_hours?: number
      min_hours?: number
      max_hours?: number
      cv?: number
      tail_risk_ratio?: number
      percentile_method?: string
    }
    distribution?: Array<{
      bin_label: string
      start_hours: number
      end_hours: number
      count: number
      pct: number
    }>
    outliers?: Array<{ vcn?: string; vessel_name?: string; status?: string; duration_hours?: number }>
    methodology?: {
      eligibility?: string
      exclusions?: string
      missing_events?: string
      percentile_method?: string
      formula_version?: string
      sample_size?: number
    }
    results?: Array<{ vcn?: string; vessel_name?: string; status?: string; duration_hours?: number }>
  } | null>(null)
  const [customError, setCustomError] = useState<string | null>(null)

  // 1. Fetch Lead Time Definitions
  const fetchDefinitions = useCallback(() => {
    setLoadingDefs(true)
    fetch(`${API}/api/v1/analytics/metrics`, { headers })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: LeadTimeDef[]) => {
        if (!Array.isArray(data)) return
        setDefinitions(data)
        if (data.length > 0 && !selectedDefId) {
          setSelectedDefId(data[0].id)
        }
        // Fetch stats for computable definitions
        data.filter((d) => d && d.availability_status === 'COMPUTABLE').forEach((d) => {
          fetch(`${API}/api/v1/analytics/metrics/${d.id}/stats`, { headers })
            .then((r) => (r.ok ? r.json() : null))
            .then((stat: MetricStat | null) => {
              if (stat) {
                setStatsMap((prev) => ({ ...prev, [d.id]: stat }))
              }
            })
            .catch(() => {})
        })
      })
      .catch((err) => console.error('Error fetching definitions:', err))
      .finally(() => setLoadingDefs(false))
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  // 2. Fetch Reconciliation Report
  const fetchReconciliation = useCallback(() => {
    setLoadingRecon(true)
    fetch(`${API}/api/v1/analytics/reconciliation?tolerance=0.02`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setReconciliation(data)
      })
      .catch((err) => console.error('Error fetching reconciliation:', err))
      .finally(() => setLoadingRecon(false))
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  // 3. Fetch Events for Builder
  const fetchEvents = useCallback(() => {
    fetch(`${API}/api/v1/analytics/events`, { headers })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: EventDef[]) => {
        if (!Array.isArray(data)) return
        setEvents(data)
        if (data.length > 1) {
          setCustomStart(data[0].name)
          setCustomEnd(data[1].name)
        }
      })
      .catch(() => {})
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  // 4. Fetch Results for Explorer
  const fetchResults = useCallback(
    (defId: string) => {
      if (!defId) return
      setLoadingResults(true)
      setSelectedResult(null)
      fetch(`${API}/api/v1/analytics/metrics/${defId}/results?limit=100`, { headers })
        .then((r) => (r.ok ? r.json() : {}))
        .then((data: { items?: PerCallResult[]; total?: number } | PerCallResult[]) => {
          if (Array.isArray(data)) {
            setResults(data)
            setResultsTotal(data.length)
          } else {
            setResults(data?.items || [])
            setResultsTotal(data?.total || 0)
          }
        })
        .catch(() => setResults([]))
        .finally(() => setLoadingResults(false))
    },
    [token] // eslint-disable-line react-hooks/exhaustive-deps
  )

  useEffect(() => {
    fetchDefinitions()
    fetchEvents()
  }, [fetchDefinitions, fetchEvents])

  useEffect(() => {
    if (activeTab === 'reconciliation') {
      fetchReconciliation()
    } else if (activeTab === 'explorer' && selectedDefId) {
      fetchResults(selectedDefId)
    }
  }, [activeTab, selectedDefId, fetchReconciliation, fetchResults])

  // Trigger Analytics Recalculation
  const handleCompute = () => {
    setRecomputing(true)
    setComputeMsg(null)
    fetch(`${API}/api/v1/analytics/compute`, { method: 'POST', headers })
      .then((r) => r.json())
      .then((data) => {
        setComputeMsg(`Calculation complete: ${data.available} available, ${data.unavailable} unavailable.`)
        fetchDefinitions()
        if (activeTab === 'reconciliation') fetchReconciliation()
        if (selectedDefId) fetchResults(selectedDefId)
      })
      .catch(() => setComputeMsg('Calculation failed'))
      .finally(() => setRecomputing(false))
  }

  // Run Custom Lead Time Calculation
  const handleRunCustom = (e: React.FormEvent) => {
    e.preventDefault()
    if (!customStart || !customEnd) return
    setCustomRunning(true)
    setCustomError(null)
    setCustomOutput(null)

    fetch(`${API}/api/v1/analytics/custom`, {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_event: customStart,
        end_event: customEnd,
        occurrence_selection: customOcc,
        movement_scope: customScope || null,
        cohort_filters: {
          vessel_type: customVesselType && customVesselType !== 'ALL' ? customVesselType : null,
          cargo_type: customCargoType && customCargoType !== 'ALL' ? customCargoType : null,
        },
        save_as_name: customSaveName || null,
      }),
    })
      .then((r) => (r.ok ? r.json() : r.json().then((err) => Promise.reject(err.detail || 'Calculation failed'))))
      .then((data) => {
        setCustomOutput(data)
        if (customSaveName) fetchDefinitions()
      })
      .catch((err) => setCustomError(String(err)))
      .finally(() => setCustomRunning(false))
  }

  return (
    <div className="flex flex-col h-full bg-slate-50 overflow-hidden">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between flex-shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-slate-900">Time and Motion Analytics</h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">
              Polars Engine · Linear Interpolation
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Governed lead-time catalogue, stage variability, tail risk, early service delivery, and golden reconciliation.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {computeMsg && <span className="text-xs text-emerald-600 font-medium">{computeMsg}</span>}
          {can('recalculate') && (
            <button
              onClick={handleCompute}
              disabled={recomputing}
              className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
            >
              {recomputing ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  Computing…
                </>
              ) : (
                <>↺ Recalculate Metrics</>
              )}
            </button>
          )}
        </div>
      </header>

      {/* ── Tab Navigation ─────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200 px-6 flex gap-2 flex-shrink-0">
        {[
          { id: 'catalogue', label: 'Governed Catalogue & Stats' },
          { id: 'reconciliation', label: 'Golden Reconciliation Scorecard' },
          { id: 'explorer', label: 'Per-Call Explorer & Lineage' },
          { id: 'custom', label: 'Custom Lead-Time Builder' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as 'catalogue' | 'reconciliation' | 'explorer' | 'custom')}
            className={`py-3 px-3 text-xs font-medium border-b-2 transition-colors ${
              activeTab === t.id
                ? 'border-emerald-600 text-emerald-700 font-semibold'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Tab Contents ───────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto p-6">
        {/* 1. Governed Catalogue & Stats */}
        {activeTab === 'catalogue' && (
          <div className="space-y-4">
            <div className="bg-white rounded-lg border border-slate-200 shadow-xs overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                <h2 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Standard Metric Catalogue ({definitions.length})
                </h2>
                <span className="text-[11px] text-slate-500">
                  Percentiles computed via linear interpolation · Quarantined records excluded by default
                </span>
              </div>

              {loadingDefs ? (
                <div className="p-8 text-center text-xs text-slate-400">Loading catalogue…</div>
              ) : (
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 font-semibold">
                      <th className="py-2.5 px-3">Metric Name</th>
                      <th className="py-2.5 px-3">Formula / Events</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3 text-right">Obs Count</th>
                      <th className="py-2.5 px-3 text-right">Mean</th>
                      <th className="py-2.5 px-3 text-right">Median</th>
                      <th className="py-2.5 px-3 text-right">P90</th>
                      <th className="py-2.5 px-3 text-right">CV (σ/μ)</th>
                      <th className="py-2.5 px-3 text-right">Tail Risk (P90/Med)</th>
                      <th className="py-2.5 px-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {definitions.map((d) => {
                      const st = statsMap[d.id]
                      const isNoSource = d.availability_status === 'NO_SOURCE_DATA'
                      return (
                        <tr key={d.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-2.5 px-3 font-semibold text-slate-800">
                            <div>{d.name}</div>
                            {d.description && <div className="text-[10px] text-slate-400 font-normal">{d.description}</div>}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600">
                            {d.is_execution_delay
                              ? `${d.execution_delay_movement} Pilotage (Served − Sched)`
                              : `${d.start_event} → ${d.end_event}`}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                isNoSource
                                  ? 'bg-slate-100 text-slate-600 border border-slate-200'
                                  : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              }`}
                            >
                              {d.availability_status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right font-medium">
                            {isNoSource ? '—' : st?.observation_count ?? '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono">
                            {isNoSource ? '—' : st?.mean_hours != null ? `${st.mean_hours.toFixed(2)}h` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono">
                            {isNoSource ? '—' : st?.median_hours != null ? `${st.median_hours.toFixed(2)}h` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono">
                            {isNoSource ? '—' : st?.p90_hours != null ? `${st.p90_hours.toFixed(2)}h` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono">
                            {isNoSource ? '—' : st?.cv != null ? st.cv.toFixed(2) : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono">
                            {isNoSource ? '—' : st?.tail_risk_ratio != null ? `${st.tail_risk_ratio.toFixed(2)}x` : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            {!isNoSource && (
                              <button
                                onClick={() => {
                                  setSelectedDefId(d.id)
                                  setActiveTab('explorer')
                                }}
                                className="text-emerald-600 hover:text-emerald-800 font-semibold text-[11px] underline"
                              >
                                Drill down
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* 2. Golden Reconciliation Scorecard */}
        {activeTab === 'reconciliation' && (
          <div className="space-y-4">
            <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-xs">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                    ExpectedOutputs Oracle Reconciliation (±0.02h Tolerance)
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Validates independently calculated vessel metrics against the governed fixture oracle (spec §21A.2, AGENTS.md §6).
                  </p>
                </div>
                {reconciliation && (
                  <div className="flex gap-2">
                    <span className="px-2 py-1 rounded text-xs font-bold bg-sky-100 text-sky-800">
                      Early Arrival Delays: {reconciliation.early_service.negative_arrival_delays}
                    </span>
                    <span className="px-2 py-1 rounded text-xs font-bold bg-sky-100 text-sky-800">
                      Early Sailing Delays: {reconciliation.early_service.negative_sailing_delays}
                    </span>
                  </div>
                )}
              </div>

              {loadingRecon ? (
                <div className="p-8 text-center text-xs text-slate-400">Comparing with oracle…</div>
              ) : !reconciliation ? (
                <div className="p-8 text-center text-xs text-slate-400">No reconciliation data available.</div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-4 gap-3">
                    <div className="bg-slate-50 border border-slate-200 rounded p-3 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Target Metrics</div>
                      <div className="text-lg font-bold text-slate-800">{reconciliation.summary.total_targets}</div>
                    </div>
                    <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-center">
                      <div className="text-[10px] uppercase font-bold text-emerald-700">Fully Reconciled</div>
                      <div className="text-lg font-bold text-emerald-800">
                        {reconciliation.summary.fully_reconciled_targets} of {reconciliation.summary.total_targets}
                      </div>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded p-3 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Total Comparisons</div>
                      <div className="text-lg font-bold text-slate-800">{reconciliation.summary.total_comparisons}</div>
                    </div>
                    <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-center">
                      <div className="text-[10px] uppercase font-bold text-emerald-700">Passed Comparisons</div>
                      <div className="text-lg font-bold text-emerald-800">
                        {reconciliation.summary.passed_comparisons} / {reconciliation.summary.total_comparisons}
                      </div>
                    </div>
                  </div>

                  <table className="w-full text-xs text-left border-collapse border border-slate-200 rounded">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50 text-slate-600 font-semibold">
                        <th className="py-2 px-3">Reconciliation Target</th>
                        <th className="py-2 px-3">Expected Column</th>
                        <th className="py-2 px-3 text-right">Eligible Calls</th>
                        <th className="py-2 px-3 text-right">Passed (±0.02h)</th>
                        <th className="py-2 px-3 text-right">Failed / Excluded</th>
                        <th className="py-2 px-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {Object.entries(reconciliation.metrics_reconciled).map(([name, m]) => {
                        const isPass = m.failed === 0 && m.passed > 0
                        return (
                          <tr key={name} className="hover:bg-slate-50">
                            <td className="py-2 px-3 font-semibold text-slate-800">{name}</td>
                            <td className="py-2 px-3 font-mono text-[11px] text-slate-500">{m.expected_metric}</td>
                            <td className="py-2 px-3 text-right">{m.total_eligible_calls}</td>
                            <td className="py-2 px-3 text-right text-emerald-700 font-semibold">{m.passed}</td>
                            <td className="py-2 px-3 text-right text-slate-600">
                              {m.failed > 0 ? (
                                <span className="text-amber-700 font-semibold">
                                  {m.failed} ({m.unavailable_in_actual} unavailable)
                                </span>
                              ) : (
                                '0'
                              )}
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  isPass ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                                }`}
                              >
                                {isPass ? '100% RECONCILED' : `${m.reconciled_fraction}`}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 3. Per-Call Explorer & Lineage */}
        {activeTab === 'explorer' && (
          <div className="grid grid-cols-3 gap-4">
            {/* Results Table */}
            <div className="col-span-2 bg-white rounded-lg border border-slate-200 shadow-xs flex flex-col">
              <div className="p-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                <div className="flex items-center gap-3">
                  <label htmlFor="metric-select" className="text-xs font-semibold text-slate-700">
                    Metric:
                  </label>
                  <select
                    id="metric-select"
                    value={selectedDefId}
                    onChange={(e) => setSelectedDefId(e.target.value)}
                    className="text-xs border border-slate-300 rounded px-2.5 py-1 bg-white focus:ring-1 focus:ring-emerald-500"
                  >
                    {definitions
                      .filter((d) => d.availability_status === 'COMPUTABLE')
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                  </select>
                </div>
                <span className="text-xs text-slate-500">Total: {resultsTotal} calls</span>
              </div>

              <div className="flex-1 overflow-y-auto max-h-[600px]">
                {loadingResults ? (
                  <div className="p-8 text-center text-xs text-slate-400">Loading results…</div>
                ) : results.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400">No calculation results found.</div>
                ) : (
                  <table className="w-full text-xs text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 sticky top-0 bg-slate-50">
                        <th className="py-2 px-3">VCN</th>
                        <th className="py-2 px-3">Vessel Name</th>
                        <th className="py-2 px-3 text-right">Duration</th>
                        <th className="py-2 px-3 text-center">Status</th>
                        <th className="py-2 px-3">Start / End (Local)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {results.map((r) => {
                        const isSelected = selectedResult?.id === r.id
                        return (
                          <tr
                            key={r.id}
                            onClick={() => setSelectedResult(r)}
                            className={`cursor-pointer transition-colors ${
                              isSelected ? 'bg-emerald-50 border-l-2 border-emerald-500' : 'hover:bg-slate-50'
                            }`}
                          >
                            <td className="py-2 px-3 font-semibold text-slate-800">{r.vcn}</td>
                            <td className="py-2 px-3 text-slate-600 truncate max-w-[140px]">{r.vessel_name || '—'}</td>
                            <td className="py-2 px-3 text-right font-mono font-medium text-slate-800">
                              {r.status === 'AVAILABLE' ? fmtHours(r.duration_hours) : '—'}
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span
                                className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                  r.status === 'AVAILABLE'
                                    ? r.duration_hours != null && r.duration_hours < 0
                                      ? 'bg-sky-100 text-sky-800'
                                      : 'bg-emerald-100 text-emerald-800'
                                    : 'bg-slate-200 text-slate-600'
                                }`}
                              >
                                {r.status === 'AVAILABLE' && r.duration_hours != null && r.duration_hours < 0
                                  ? 'EARLY SERVICE'
                                  : r.status}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-[10px] text-slate-500">
                              {r.start_time ? fmtTs(r.start_time).split(',')[1] : '—'} →{' '}
                              {r.end_time ? fmtTs(r.end_time).split(',')[1] : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Traceability Envelope Drawer */}
            <div className="bg-white rounded-lg border border-slate-200 shadow-xs p-4 flex flex-col">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide border-b border-slate-200 pb-2 mb-3">
                Traceability Envelope (Spec §2 & §10)
              </h3>

              {!selectedResult ? (
                <div className="flex-1 flex items-center justify-center text-xs text-slate-400 text-center px-4">
                  Select a vessel call row to inspect formula lineage, contributing source IDs, filter context, and DQ status.
                </div>
              ) : (
                <div className="space-y-3 text-xs overflow-y-auto">
                  <div>
                    <span className="text-slate-500 font-medium">VCN:</span>{' '}
                    <span className="font-bold text-slate-800">{selectedResult.vcn}</span>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Status:</span>{' '}
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                        selectedResult.status === 'AVAILABLE' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {selectedResult.status}
                    </span>
                    {selectedResult.unavailable_reason && (
                      <p className="text-red-600 text-[11px] mt-1 bg-red-50 p-2 rounded border border-red-200">
                        {selectedResult.unavailable_reason}
                      </p>
                    )}
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Duration:</span>{' '}
                    <span className="font-mono font-bold text-slate-900">
                      {fmtHours(selectedResult.duration_hours)}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Start Timestamp:</span>
                    <div className="font-mono text-[11px] text-slate-700">{fmtTs(selectedResult.start_time)}</div>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">End Timestamp:</span>
                    <div className="font-mono text-[11px] text-slate-700">{fmtTs(selectedResult.end_time)}</div>
                  </div>

                  <div className="pt-2 border-t border-slate-100">
                    <span className="text-slate-500 font-medium">Formula Version:</span>{' '}
                    <span className="font-mono text-slate-700">{selectedResult.traceability.formula_version || '1.0'}</span>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Data Quality Status:</span>{' '}
                    <span className="font-semibold text-slate-700">{selectedResult.traceability.dq_status || 'CLEAN'}</span>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Contributing Source IDs:</span>
                    <div className="bg-slate-50 p-2 rounded border border-slate-200 mt-1 max-h-24 overflow-y-auto space-y-1">
                      {selectedResult.traceability.source_record_ids.length > 0 ? (
                        selectedResult.traceability.source_record_ids.map((id) => (
                          <div key={id} className="font-mono text-[10px] text-slate-600 truncate">
                            {id}
                          </div>
                        ))
                      ) : (
                        <div className="text-[10px] text-slate-400 italic">None recorded</div>
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="text-slate-500 font-medium">Calculated At:</span>
                    <div className="text-[10px] text-slate-400">{fmtTs(selectedResult.traceability.calculated_at)}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 4. Custom Lead-Time Builder */}
        {activeTab === 'custom' && (
          <div className="grid grid-cols-3 gap-6">
            {/* Builder Form */}
            <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-xs">
              <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide border-b border-slate-200 pb-2 mb-4">
                Custom Lead-Time Configuration
              </h2>

              <form onSubmit={handleRunCustom} className="space-y-4 text-xs">
                <div>
                  <label htmlFor="start-event-select" className="block text-slate-600 font-semibold mb-1">
                    Start Event
                  </label>
                  <select
                    id="start-event-select"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  >
                    {events.map((ev) => (
                      <option key={ev.id} value={ev.name}>
                        {ev.name} {ev.category ? `(${ev.category})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="end-event-select" className="block text-slate-600 font-semibold mb-1">
                    End Event
                  </label>
                  <select
                    id="end-event-select"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white focus:ring-1 focus:ring-emerald-500"
                  >
                    {events.map((ev) => (
                      <option key={ev.id} value={ev.name}>
                        {ev.name} {ev.category ? `(${ev.category})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="occurrence-select" className="block text-slate-600 font-semibold mb-1">
                    Occurrence Selection
                  </label>
                  <select
                    id="occurrence-select"
                    value={customOcc}
                    onChange={(e) => setCustomOcc(e.target.value)}
                    className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                  >
                    <option value="first">First occurrence</option>
                    <option value="last">Last occurrence</option>
                    <option value="all">All occurrences (pairwise)</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="movement-scope-select" className="block text-slate-600 font-semibold mb-1">
                    Movement Scope (Optional)
                  </label>
                  <select
                    id="movement-scope-select"
                    value={customScope}
                    onChange={(e) => setCustomScope(e.target.value)}
                    className="w-full border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                  >
                    <option value="">Any scope</option>
                    <option value="ARRIVAL">ARRIVAL</option>
                    <option value="SAILING">SAILING</option>
                    <option value="SHIFTING">SHIFTING</option>
                  </select>
                </div>

                <div className="pt-2 border-t border-slate-100">
                  <div className="font-semibold text-slate-700 mb-2">Cohort Filters</div>
                  <div className="space-y-2">
                    <div>
                      <label htmlFor="cohort-vessel-type" className="block text-slate-500 text-[11px] mb-0.5">
                        Vessel Type
                      </label>
                      <select
                        id="cohort-vessel-type"
                        value={customVesselType}
                        onChange={(e) => setCustomVesselType(e.target.value)}
                        className="w-full border border-slate-300 rounded px-2 py-1 bg-white"
                      >
                        <option value="">All Vessel Types</option>
                        <option value="Fully Cellular Containership">Fully Cellular Containership</option>
                        <option value="Bulk Carrier">Bulk Carrier</option>
                        <option value="Product Tanker">Product Tanker</option>
                        <option value="Vehicle Carrier">Vehicle Carrier</option>
                      </select>
                    </div>

                    <div>
                      <label htmlFor="cohort-cargo-type" className="block text-slate-500 text-[11px] mb-0.5">
                        Cargo Type
                      </label>
                      <select
                        id="cohort-cargo-type"
                        value={customCargoType}
                        onChange={(e) => setCustomCargoType(e.target.value)}
                        className="w-full border border-slate-300 rounded px-2 py-1 bg-white"
                      >
                        <option value="">All Cargo Types</option>
                        <option value="Container">Container</option>
                        <option value="Bulk">Bulk</option>
                        <option value="Liquid Bulk">Liquid Bulk</option>
                        <option value="RoRo">RoRo</option>
                        <option value="Break Bulk">Break Bulk</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100">
                  <label htmlFor="save-name-input" className="block text-slate-600 font-semibold mb-1">
                    Save as Catalogue Metric (Optional)
                  </label>
                  <input
                    id="save-name-input"
                    type="text"
                    placeholder="e.g. Custom Pilot-to-All-Fast"
                    value={customSaveName}
                    onChange={(e) => setCustomSaveName(e.target.value)}
                    className="w-full border border-slate-300 rounded px-2.5 py-1.5"
                  />
                </div>

                {customError && <div className="text-red-600 bg-red-50 p-2 rounded text-xs">{customError}</div>}

                <button
                  type="submit"
                  disabled={customRunning}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded py-2 font-semibold transition-colors disabled:opacity-50"
                >
                  {customRunning ? 'Computing…' : 'Calculate Custom Lead Time'}
                </button>
              </form>
            </div>

            {/* Custom Output */}
            <div className="col-span-2 space-y-4">
              {!customOutput ? (
                <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-xs text-slate-400">
                  Configure an event pair on the left and run the calculation to view Polars statistics and per-call results.
                </div>
              ) : (
                <>
                  {/* 1. Extended Summary Cards */}
                  <div className="grid grid-cols-6 gap-2 text-xs">
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Sample Size</div>
                      <div className="text-base font-bold text-slate-800 font-mono">
                        {customOutput.aggregate?.observation_count ?? 0}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {customOutput.aggregate?.missing_count ?? 0} missing
                      </div>
                    </div>
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Mean Duration</div>
                      <div className="text-base font-bold text-emerald-700 font-mono">
                        {customOutput.aggregate?.mean_hours != null ? `${customOutput.aggregate.mean_hours.toFixed(2)}h` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">Average</div>
                    </div>
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Median (P50)</div>
                      <div className="text-base font-bold text-emerald-700 font-mono">
                        {customOutput.aggregate?.median_hours != null ? `${customOutput.aggregate.median_hours.toFixed(2)}h` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">50th percentile</div>
                    </div>
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">P90 Tail Risk</div>
                      <div className="text-base font-bold text-amber-700 font-mono">
                        {customOutput.aggregate?.p90_hours != null ? `${customOutput.aggregate.p90_hours.toFixed(2)}h` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">90th percentile</div>
                    </div>
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Minimum</div>
                      <div className="text-base font-bold text-slate-700 font-mono">
                        {customOutput.aggregate?.min_hours != null ? `${customOutput.aggregate.min_hours.toFixed(2)}h` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">Fastest call</div>
                    </div>
                    <div className="bg-white border border-slate-200 rounded p-2.5 text-center">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Maximum</div>
                      <div className="text-base font-bold text-slate-700 font-mono">
                        {customOutput.aggregate?.max_hours != null ? `${customOutput.aggregate.max_hours.toFixed(2)}h` : '—'}
                      </div>
                      <div className="text-[10px] text-slate-400">Slowest call</div>
                    </div>
                  </div>

                  {/* 2. Distribution Visualization (Histogram) */}
                  {customOutput.distribution && customOutput.distribution.length > 0 && (
                    <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-xs">
                      <div className="flex items-center justify-between mb-3 text-xs">
                        <span className="font-bold text-slate-700 uppercase tracking-wide">
                          Duration Distribution Frequency
                        </span>
                        <span className="text-[11px] text-slate-500">5-Bin Linear Histogram</span>
                      </div>
                      <div className="space-y-2">
                        {customOutput.distribution.map((bin, idx) => (
                          <div key={idx} className="text-xs">
                            <div className="flex items-center justify-between text-[11px] mb-1 font-mono">
                              <span className="text-slate-600 font-medium">{bin.bin_label}</span>
                              <span className="text-slate-500 font-bold">
                                {bin.count} calls ({bin.pct}%)
                              </span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden border border-slate-200">
                              <div
                                className="bg-emerald-600 h-full rounded-full transition-all"
                                style={{ width: `${Math.max(2, bin.pct)}%` }}
                              ></div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 3. Methodology & Governance Explanation */}
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs">
                    <div className="font-bold text-slate-700 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
                      <span>📖</span>
                      <span>Governed Methodology & Calculations</span>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-[11px] text-slate-600">
                      <div>
                        <strong>Eligibility:</strong> {customOutput.methodology?.eligibility || 'Active non-merged calls'}
                      </div>
                      <div>
                        <strong>Exclusions:</strong> {customOutput.methodology?.exclusions || 'Quarantined excluded'}
                      </div>
                      <div>
                        <strong>Missing Events:</strong> {customOutput.methodology?.missing_events || 'Reported as UNAVAILABLE'}
                      </div>
                      <div>
                        <strong>Percentile Method:</strong> {customOutput.methodology?.percentile_method || 'Linear interpolation'}
                      </div>
                      <div>
                        <strong>Formula Version:</strong> {customOutput.methodology?.formula_version || '1.0'}
                      </div>
                      <div>
                        <strong>Sample Size:</strong> {customOutput.methodology?.sample_size ?? customOutput.aggregate?.observation_count} calls
                      </div>
                    </div>
                  </div>

                  {/* 4. Outliers Table */}
                  {customOutput.outliers && customOutput.outliers.length > 0 && (
                    <div className="bg-amber-50/60 border border-amber-200 rounded-lg p-3 text-xs">
                      <div className="font-bold text-amber-900 uppercase tracking-wide mb-2 flex items-center justify-between">
                        <span>⚠ Detected Tail Outliers ({customOutput.outliers.length})</span>
                        <span className="text-[10px] font-normal text-amber-700 font-mono">
                          Duration &gt; P90 ({customOutput.aggregate?.p90_hours?.toFixed(1)}h) or negative
                        </span>
                      </div>
                      <div className="max-h-32 overflow-y-auto space-y-1">
                        {customOutput.outliers.map((o, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between bg-white/80 px-2 py-1 rounded border border-amber-200/60 text-[11px]"
                          >
                            <span className="font-mono font-bold text-amber-900">{o.vcn}</span>
                            <span className="text-slate-600">{o.vessel_name || '—'}</span>
                            <span className="font-mono font-bold text-amber-800">{fmtHours(o.duration_hours)}</span>
                            <Link
                              href={`/vessel-journey?vcn=${o.vcn}`}
                              className="text-emerald-600 hover:underline font-semibold text-[10px]"
                            >
                              Inspect Journey →
                            </Link>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 5. Results Table */}
                  <div className="bg-white rounded-lg border border-slate-200 shadow-xs overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-700">{customOutput.formula}</span>
                      <span className="text-[11px] text-slate-500">
                        {customOutput.results?.length || 0} vessel calls analyzed
                      </span>
                    </div>

                    <div className="max-h-[300px] overflow-y-auto">
                      <table className="w-full text-xs text-left border-collapse">
                        <thead>
                          <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 font-semibold">
                            <th className="py-2 px-3">VCN</th>
                            <th className="py-2 px-3">Vessel Name</th>
                            <th className="py-2 px-3 text-right">Duration</th>
                            <th className="py-2 px-3 text-center">Status</th>
                            <th className="py-2 px-3 text-center">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {customOutput.results?.map((r, idx: number) => (
                            <tr key={idx} className="hover:bg-slate-50">
                              <td className="py-1.5 px-3 font-semibold text-slate-800 font-mono">{r.vcn}</td>
                              <td className="py-1.5 px-3 text-slate-600">{r.vessel_name || '—'}</td>
                              <td className="py-1.5 px-3 text-right font-mono font-medium">
                                {r.status === 'AVAILABLE' ? fmtHours(r.duration_hours) : '—'}
                              </td>
                              <td className="py-1.5 px-3 text-center">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                    r.status === 'AVAILABLE' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                                  }`}
                                >
                                  {r.status}
                                </span>
                              </td>
                              <td className="py-1.5 px-3 text-center">
                                <Link
                                  href={`/vessel-journey?vcn=${r.vcn}`}
                                  className="text-emerald-600 hover:underline font-semibold text-[11px]"
                                >
                                  Drill down
                                </Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default function TimeAndMotionPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center bg-slate-50 text-slate-400 text-xs font-mono">
          Loading Time & Motion Explorer…
        </div>
      }
    >
      <TimeAndMotionContent />
    </React.Suspense>
  )
}
