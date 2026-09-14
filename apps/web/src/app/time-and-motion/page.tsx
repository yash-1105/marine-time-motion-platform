'use client'

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth-context'
import {
  PageHeader,
  SectionHeader,
  Card,
  KpiCard,
  StatusBadge,
  EmptyState,
  LoadingState,
  ErrorState,
  FilterField,
} from '@/components/ui'

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
    <div className="flex flex-col h-full bg-[var(--color-bg)] overflow-hidden">
      {/* ── Top Header ──────────────────────────────────────────────────────── */}
      <PageHeader
        title="Time & Motion Explorer"
        meta={
          <StatusBadge label="Polars Engine · Linear Interpolation" tone="good" showGlyph={false} />
        }
        actions={
          <div className="flex items-center gap-3">
            {computeMsg && <span className="text-xs text-[var(--color-good)] font-medium">{computeMsg}</span>}
            {can('recalculate') && (
              <button
                onClick={handleCompute}
                disabled={recomputing}
                className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 cursor-pointer"
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
        }
      />

      {/* ── Tab Navigation ─────────────────────────────────────────────────── */}
      <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 flex gap-2 flex-shrink-0">
        {[
          { id: 'catalogue', label: 'Governed Catalogue & Stats' },
          { id: 'reconciliation', label: 'Golden Reconciliation Scorecard' },
          { id: 'explorer', label: 'Per-Call Explorer & Lineage' },
          { id: 'custom', label: 'Custom Lead-Time Builder' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as 'catalogue' | 'reconciliation' | 'explorer' | 'custom')}
            className={`py-3 px-3 text-xs font-medium border-b-2 transition-colors cursor-pointer ${
              activeTab === t.id
                ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-semibold'
                : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]'
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
            <SectionHeader
              title={`Standard Metric Catalogue (${definitions.length})`}
              description="Percentiles computed via linear interpolation · Quarantined records excluded by default"
            />
            <Card padded={false} className="overflow-hidden">
              {loadingDefs ? (
                <LoadingState label="Loading catalogue…" />
              ) : definitions.length === 0 ? (
                <EmptyState title="No metric definitions found" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-semibold">
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
                    <tbody className="divide-y divide-[var(--color-border)]">
                      {definitions.map((d) => {
                        const st = statsMap[d.id]
                        const isNoSource = d.availability_status === 'NO_SOURCE_DATA'
                        return (
                          <tr key={d.id} className="hover:bg-[var(--color-surface-muted)] transition-colors">
                            <td className="py-2.5 px-3 font-semibold text-[var(--color-text-primary)]">
                              <div>{d.name}</div>
                              {d.description && (
                                <div className="text-[10px] text-[var(--color-text-tertiary)] font-normal">{d.description}</div>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-[11px] text-[var(--color-text-secondary)]">
                              {d.is_execution_delay
                                ? `${d.execution_delay_movement} Pilotage (Served − Sched)`
                                : `${d.start_event} → ${d.end_event}`}
                            </td>
                            <td className="py-2.5 px-3">
                              <StatusBadge status={d.availability_status} tone={isNoSource ? 'neutral' : 'good'} />
                            </td>
                            <td className="py-2.5 px-3 text-right font-medium text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.observation_count ?? '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.mean_hours != null ? `${st.mean_hours.toFixed(2)}h` : '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.median_hours != null ? `${st.median_hours.toFixed(2)}h` : '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.p90_hours != null ? `${st.p90_hours.toFixed(2)}h` : '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.cv != null ? st.cv.toFixed(2) : '—'}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono text-[var(--color-text-primary)]">
                              {isNoSource ? '—' : st?.tail_risk_ratio != null ? `${st.tail_risk_ratio.toFixed(2)}x` : '—'}
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              {!isNoSource && (
                                <button
                                  onClick={() => {
                                    setSelectedDefId(d.id)
                                    setActiveTab('explorer')
                                  }}
                                  className="text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] font-semibold text-[11px] underline cursor-pointer"
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
                </div>
              )}
            </Card>
          </div>
        )}

        {/* 2. Golden Reconciliation Scorecard */}
        {activeTab === 'reconciliation' && (
          <div className="space-y-4">
            <SectionHeader
              title="ExpectedOutputs Oracle Reconciliation (±0.02h Tolerance)"
              description="Validates independently calculated vessel metrics against the governed fixture oracle (spec §21A.2, AGENTS.md §6)."
              action={
                reconciliation && (
                  <div className="flex gap-2">
                    <StatusBadge
                      tone="inferred"
                      showGlyph={false}
                      label={`Early Arrival Delays: ${reconciliation.early_service.negative_arrival_delays}`}
                    />
                    <StatusBadge
                      tone="inferred"
                      showGlyph={false}
                      label={`Early Sailing Delays: ${reconciliation.early_service.negative_sailing_delays}`}
                    />
                  </div>
                )
              }
            />

            <Card>
              {loadingRecon ? (
                <LoadingState label="Comparing with oracle…" />
              ) : !reconciliation ? (
                <EmptyState title="No reconciliation data available" />
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <KpiCard label="Target Metrics" value={reconciliation.summary.total_targets} />
                    <KpiCard
                      label="Fully Reconciled"
                      value={`${reconciliation.summary.fully_reconciled_targets} / ${reconciliation.summary.total_targets}`}
                      tone="good"
                    />
                    <KpiCard label="Total Comparisons" value={reconciliation.summary.total_comparisons} />
                    <KpiCard
                      label="Passed Comparisons"
                      value={`${reconciliation.summary.passed_comparisons} / ${reconciliation.summary.total_comparisons}`}
                      tone="good"
                    />
                  </div>

                  <div className="overflow-x-auto border border-[var(--color-border)] rounded-lg">
                    <table className="w-full text-xs text-left border-collapse">
                      <thead>
                        <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-semibold">
                          <th className="py-2 px-3">Reconciliation Target</th>
                          <th className="py-2 px-3">Expected Column</th>
                          <th className="py-2 px-3 text-right">Eligible Calls</th>
                          <th className="py-2 px-3 text-right">Passed (±0.02h)</th>
                          <th className="py-2 px-3 text-right">Failed / Excluded</th>
                          <th className="py-2 px-3 text-center">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--color-border)]">
                        {Object.entries(reconciliation.metrics_reconciled).map(([name, m]) => {
                          const isPass = m.failed === 0 && m.passed > 0
                          return (
                            <tr key={name} className="hover:bg-[var(--color-surface-muted)]">
                              <td className="py-2 px-3 font-semibold text-[var(--color-text-primary)]">{name}</td>
                              <td className="py-2 px-3 font-mono text-[11px] text-[var(--color-text-secondary)]">{m.expected_metric}</td>
                              <td className="py-2 px-3 text-right text-[var(--color-text-primary)]">{m.total_eligible_calls}</td>
                              <td className="py-2 px-3 text-right text-[var(--color-good)] font-semibold">{m.passed}</td>
                              <td className="py-2 px-3 text-right text-[var(--color-text-secondary)]">
                                {m.failed > 0 ? (
                                  <span className="text-[var(--color-warning)] font-semibold">
                                    {m.failed} ({m.unavailable_in_actual} unavailable)
                                  </span>
                                ) : (
                                  '0'
                                )}
                              </td>
                              <td className="py-2 px-3 text-center">
                                <StatusBadge
                                  tone={isPass ? 'good' : 'warning'}
                                  label={isPass ? '100% Reconciled' : m.reconciled_fraction}
                                />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* 3. Per-Call Explorer & Lineage */}
        {activeTab === 'explorer' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Results Table */}
            <Card padded={false} className="lg:col-span-2 flex flex-col overflow-hidden">
              <div className="p-3 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-surface-muted)]">
                <FilterField label="Metric" className="w-64">
                  <select
                    id="metric-select"
                    value={selectedDefId}
                    onChange={(e) => setSelectedDefId(e.target.value)}
                    className="w-full text-xs border border-[var(--color-border)] rounded-md px-2.5 py-1 bg-[var(--color-surface)] focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none cursor-pointer"
                  >
                    {definitions
                      .filter((d) => d.availability_status === 'COMPUTABLE')
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                  </select>
                </FilterField>
                <span className="text-xs text-[var(--color-text-secondary)]">Total: {resultsTotal} calls</span>
              </div>

              <div className="flex-1 overflow-y-auto max-h-[600px]">
                {loadingResults ? (
                  <LoadingState label="Loading results…" />
                ) : results.length === 0 ? (
                  <EmptyState title="No calculation results found" />
                ) : (
                  <table className="w-full text-xs text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] sticky top-0">
                        <th className="py-2 px-3">VCN</th>
                        <th className="py-2 px-3">Vessel Name</th>
                        <th className="py-2 px-3 text-right">Duration</th>
                        <th className="py-2 px-3 text-center">Status</th>
                        <th className="py-2 px-3">Start / End (Local)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--color-border)]">
                      {results.map((r) => {
                        const isSelected = selectedResult?.id === r.id
                        const isEarly = r.status === 'AVAILABLE' && r.duration_hours != null && r.duration_hours < 0
                        return (
                          <tr
                            key={r.id}
                            onClick={() => setSelectedResult(r)}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-[var(--color-accent-soft)] border-l-2 border-[var(--color-accent)]'
                                : 'hover:bg-[var(--color-surface-muted)]'
                            }`}
                          >
                            <td className="py-2 px-3 font-semibold text-[var(--color-text-primary)]">{r.vcn}</td>
                            <td className="py-2 px-3 text-[var(--color-text-secondary)] truncate max-w-[140px]">
                              {r.vessel_name || '—'}
                            </td>
                            <td className="py-2 px-3 text-right font-mono font-medium text-[var(--color-text-primary)]">
                              {r.status === 'AVAILABLE' ? fmtHours(r.duration_hours) : '—'}
                            </td>
                            <td className="py-2 px-3 text-center">
                              <StatusBadge
                                tone={r.status === 'AVAILABLE' ? (isEarly ? 'inferred' : 'good') : 'neutral'}
                                label={isEarly ? 'Early Service' : r.status}
                              />
                            </td>
                            <td className="py-2 px-3 text-[10px] text-[var(--color-text-tertiary)]">
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
            </Card>

            {/* Traceability Envelope Drawer */}
            <Card className="flex flex-col">
              <SectionHeader title="Traceability Envelope (Spec §2 & §10)" className="border-b border-[var(--color-border)] pb-3" />

              {!selectedResult ? (
                <EmptyState
                  title="No call selected"
                  description="Select a vessel call row to inspect formula lineage, contributing source IDs, filter context, and DQ status."
                />
              ) : (
                <div className="space-y-3 text-xs overflow-y-auto">
                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">VCN:</span>{' '}
                    <span className="font-bold text-[var(--color-text-primary)]">{selectedResult.vcn}</span>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Status:</span>{' '}
                    <StatusBadge tone={selectedResult.status === 'AVAILABLE' ? 'good' : 'neutral'} label={selectedResult.status} />
                    {selectedResult.unavailable_reason && (
                      <p className="text-[var(--color-critical)] text-[11px] mt-1 bg-[var(--color-critical-bg)] p-2 rounded border border-[var(--color-critical-border)]">
                        {selectedResult.unavailable_reason}
                      </p>
                    )}
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Duration:</span>{' '}
                    <span className="font-mono font-bold text-[var(--color-text-primary)]">
                      {fmtHours(selectedResult.duration_hours)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Start Timestamp:</span>
                    <div className="font-mono text-[11px] text-[var(--color-text-primary)]">{fmtTs(selectedResult.start_time)}</div>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">End Timestamp:</span>
                    <div className="font-mono text-[11px] text-[var(--color-text-primary)]">{fmtTs(selectedResult.end_time)}</div>
                  </div>

                  <div className="pt-2 border-t border-[var(--color-border)]">
                    <span className="text-[var(--color-text-secondary)] font-medium">Formula Version:</span>{' '}
                    <span className="font-mono text-[var(--color-text-primary)]">{selectedResult.traceability.formula_version || '1.0'}</span>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Data Quality Status:</span>{' '}
                    <span className="font-semibold text-[var(--color-text-primary)]">{selectedResult.traceability.dq_status || 'CLEAN'}</span>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Contributing Source IDs:</span>
                    <div className="bg-[var(--color-surface-muted)] p-2 rounded border border-[var(--color-border)] mt-1 max-h-24 overflow-y-auto space-y-1">
                      {selectedResult.traceability.source_record_ids.length > 0 ? (
                        selectedResult.traceability.source_record_ids.map((id) => (
                          <div key={id} className="font-mono text-[10px] text-[var(--color-text-secondary)] truncate">
                            {id}
                          </div>
                        ))
                      ) : (
                        <div className="text-[10px] text-[var(--color-text-tertiary)] italic">None recorded</div>
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="text-[var(--color-text-secondary)] font-medium">Calculated At:</span>
                    <div className="text-[10px] text-[var(--color-text-tertiary)]">{fmtTs(selectedResult.traceability.calculated_at)}</div>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* 4. Custom Lead-Time Builder */}
        {activeTab === 'custom' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Builder Form */}
            <Card>
              <SectionHeader title="Custom Lead-Time Configuration" className="border-b border-[var(--color-border)] pb-3" />

              <form onSubmit={handleRunCustom} className="space-y-5 text-xs">
                {/* Event Range group */}
                <div>
                  <div className="text-[10px] uppercase font-bold tracking-wide text-[var(--color-text-tertiary)] mb-2">
                    Event Range
                  </div>
                  <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3">
                    <FilterField label="Start Event">
                      <select
                        id="start-event-select"
                        value={customStart}
                        onChange={(e) => setCustomStart(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2.5 py-1.5 bg-[var(--color-surface)] focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none cursor-pointer"
                      >
                        {events.map((ev) => (
                          <option key={ev.id} value={ev.name}>
                            {ev.name} {ev.category ? `(${ev.category})` : ''}
                          </option>
                        ))}
                      </select>
                    </FilterField>

                    <FilterField label="End Event">
                      <select
                        id="end-event-select"
                        value={customEnd}
                        onChange={(e) => setCustomEnd(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2.5 py-1.5 bg-[var(--color-surface)] focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none cursor-pointer"
                      >
                        {events.map((ev) => (
                          <option key={ev.id} value={ev.name}>
                            {ev.name} {ev.category ? `(${ev.category})` : ''}
                          </option>
                        ))}
                      </select>
                    </FilterField>

                    <FilterField label="Occurrence Selection">
                      <select
                        id="occurrence-select"
                        value={customOcc}
                        onChange={(e) => setCustomOcc(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2.5 py-1.5 bg-[var(--color-surface)] cursor-pointer"
                      >
                        <option value="first">First occurrence</option>
                        <option value="last">Last occurrence</option>
                        <option value="all">All occurrences (pairwise)</option>
                      </select>
                    </FilterField>

                    <FilterField label="Movement Scope (Optional)">
                      <select
                        id="movement-scope-select"
                        value={customScope}
                        onChange={(e) => setCustomScope(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2.5 py-1.5 bg-[var(--color-surface)] cursor-pointer"
                      >
                        <option value="">Any scope</option>
                        <option value="ARRIVAL">ARRIVAL</option>
                        <option value="SAILING">SAILING</option>
                        <option value="SHIFTING">SHIFTING</option>
                      </select>
                    </FilterField>
                  </div>
                </div>

                {/* Cohort group */}
                <div>
                  <div className="text-[10px] uppercase font-bold tracking-wide text-[var(--color-text-tertiary)] mb-2">
                    Cohort
                  </div>
                  <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3">
                    <FilterField label="Vessel Type">
                      <select
                        id="cohort-vessel-type"
                        value={customVesselType}
                        onChange={(e) => setCustomVesselType(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2 py-1 bg-[var(--color-surface)] cursor-pointer"
                      >
                        <option value="">All Vessel Types</option>
                        <option value="Fully Cellular Containership">Fully Cellular Containership</option>
                        <option value="Bulk Carrier">Bulk Carrier</option>
                        <option value="Product Tanker">Product Tanker</option>
                        <option value="Vehicle Carrier">Vehicle Carrier</option>
                      </select>
                    </FilterField>

                    <FilterField label="Cargo Type">
                      <select
                        id="cohort-cargo-type"
                        value={customCargoType}
                        onChange={(e) => setCustomCargoType(e.target.value)}
                        className="w-full border border-[var(--color-border)] rounded-md px-2 py-1 bg-[var(--color-surface)] cursor-pointer"
                      >
                        <option value="">All Cargo Types</option>
                        <option value="Container">Container</option>
                        <option value="Bulk">Bulk</option>
                        <option value="Liquid Bulk">Liquid Bulk</option>
                        <option value="RoRo">RoRo</option>
                        <option value="Break Bulk">Break Bulk</option>
                      </select>
                    </FilterField>
                  </div>
                </div>

                <div className="pt-1 border-t border-[var(--color-border)]">
                  <FilterField label="Save as Catalogue Metric (Optional)" className="mt-3">
                    <input
                      id="save-name-input"
                      type="text"
                      placeholder="e.g. Custom Pilot-to-All-Fast"
                      value={customSaveName}
                      onChange={(e) => setCustomSaveName(e.target.value)}
                      className="w-full border border-[var(--color-border)] rounded-md px-2.5 py-1.5 bg-[var(--color-surface)]"
                    />
                  </FilterField>
                </div>

                {customError && (
                  <ErrorState
                    title="Calculation failed"
                    description={customError}
                    onRetry={() => setCustomError(null)}
                    className="py-4"
                  />
                )}

                <button
                  type="submit"
                  disabled={customRunning}
                  className="w-full bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md py-2 font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                >
                  {customRunning ? 'Computing…' : 'Calculate Custom Lead Time'}
                </button>
              </form>
            </Card>

            {/* Custom Output */}
            <div className="lg:col-span-2 space-y-4">
              {!customOutput ? (
                <Card>
                  <EmptyState
                    title="No calculation run yet"
                    description="Configure an event range and cohort on the left and run the calculation to view statistics and per-call results."
                  />
                </Card>
              ) : (
                <>
                  {/* 1. Extended Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs">
                    <KpiCard
                      label="Sample Size"
                      value={customOutput.aggregate?.observation_count ?? 0}
                      context={`${customOutput.aggregate?.missing_count ?? 0} missing`}
                    />
                    <KpiCard
                      label="Mean Duration"
                      value={customOutput.aggregate?.mean_hours != null ? `${customOutput.aggregate.mean_hours.toFixed(2)}h` : '—'}
                      context="Average"
                    />
                    <KpiCard
                      label="Median (P50)"
                      value={customOutput.aggregate?.median_hours != null ? `${customOutput.aggregate.median_hours.toFixed(2)}h` : '—'}
                      context="50th percentile"
                    />
                    <KpiCard
                      label="P90 Tail Risk"
                      value={customOutput.aggregate?.p90_hours != null ? `${customOutput.aggregate.p90_hours.toFixed(2)}h` : '—'}
                      context="90th percentile"
                    />
                    <KpiCard
                      label="Minimum"
                      value={customOutput.aggregate?.min_hours != null ? `${customOutput.aggregate.min_hours.toFixed(2)}h` : '—'}
                      context="Fastest call"
                    />
                    <KpiCard
                      label="Maximum"
                      value={customOutput.aggregate?.max_hours != null ? `${customOutput.aggregate.max_hours.toFixed(2)}h` : '—'}
                      context="Slowest call"
                    />
                  </div>

                  {/* 2. Distribution Visualization (Histogram) */}
                  {customOutput.distribution && customOutput.distribution.length > 0 && (
                    <Card>
                      <SectionHeader
                        title="Duration Distribution Frequency"
                        description="5-bin linear histogram"
                      />
                      <div className="space-y-2">
                        {customOutput.distribution.map((bin, idx) => (
                          <div key={idx} className="text-xs">
                            <div className="flex items-center justify-between text-[11px] mb-1 font-mono">
                              <span className="text-[var(--color-text-secondary)] font-medium">{bin.bin_label}</span>
                              <span className="text-[var(--color-text-secondary)] font-bold">
                                {bin.count} calls ({bin.pct}%)
                              </span>
                            </div>
                            <div className="w-full bg-[var(--color-surface-muted)] rounded-full h-2 overflow-hidden border border-[var(--color-border)]">
                              <div
                                className="bg-[var(--color-accent)] h-full rounded-full transition-all"
                                style={{ width: `${Math.max(2, bin.pct)}%` }}
                              ></div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  {/* 3. Methodology & Governance Explanation (collapsible, low-emphasis) */}
                  <details className="group bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg text-xs">
                    <summary className="cursor-pointer select-none px-3 py-2.5 text-[var(--color-text-secondary)] font-medium flex items-center justify-between">
                      <span>Governed Methodology &amp; Calculations</span>
                      <span className="text-[var(--color-text-tertiary)] transition-transform group-open:rotate-180">⌄</span>
                    </summary>
                    <div className="px-3 pb-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px] text-[var(--color-text-secondary)] border-t border-[var(--color-border)] pt-3">
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Eligibility:</strong>{' '}
                        {customOutput.methodology?.eligibility || 'Active non-merged calls'}
                      </div>
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Exclusions:</strong>{' '}
                        {customOutput.methodology?.exclusions || 'Quarantined excluded'}
                      </div>
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Missing Events:</strong>{' '}
                        {customOutput.methodology?.missing_events || 'Reported as UNAVAILABLE'}
                      </div>
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Percentile Method:</strong>{' '}
                        {customOutput.methodology?.percentile_method || 'Linear interpolation'}
                      </div>
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Formula Version:</strong>{' '}
                        {customOutput.methodology?.formula_version || '1.0'}
                      </div>
                      <div>
                        <strong className="text-[var(--color-text-primary)]">Sample Size:</strong>{' '}
                        {customOutput.methodology?.sample_size ?? customOutput.aggregate?.observation_count} calls
                      </div>
                    </div>
                  </details>

                  {/* 4. Outliers Table */}
                  {customOutput.outliers && customOutput.outliers.length > 0 && (
                    <Card className="!p-3">
                      <div className="font-semibold text-[var(--color-text-primary)] mb-2 flex items-center justify-between text-xs">
                        <StatusBadge tone="warning" label={`Detected Tail Outliers (${customOutput.outliers.length})`} />
                        <span className="text-[10px] font-normal text-[var(--color-text-tertiary)] font-mono">
                          Duration &gt; P90 ({customOutput.aggregate?.p90_hours?.toFixed(1)}h) or negative
                        </span>
                      </div>
                      <div className="max-h-32 overflow-y-auto space-y-1">
                        {customOutput.outliers.map((o, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between bg-[var(--color-warning-bg)] px-2 py-1 rounded border border-[var(--color-warning-border)] text-[11px]"
                          >
                            <span className="font-mono font-bold text-[var(--color-warning)]">{o.vcn}</span>
                            <span className="text-[var(--color-text-secondary)]">{o.vessel_name || '—'}</span>
                            <span className="font-mono font-bold text-[var(--color-warning)]">{fmtHours(o.duration_hours)}</span>
                            <Link
                              href={`/vessel-journey?vcn=${o.vcn}`}
                              className="text-[var(--color-accent)] hover:underline font-semibold text-[10px]"
                            >
                              Inspect Journey →
                            </Link>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  {/* 5. Results Table */}
                  <Card padded={false} className="overflow-hidden">
                    <div className="px-4 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] flex items-center justify-between text-xs">
                      <span className="font-semibold text-[var(--color-text-primary)]">{customOutput.formula}</span>
                      <span className="text-[11px] text-[var(--color-text-secondary)]">
                        {customOutput.results?.length || 0} vessel calls analyzed
                      </span>
                    </div>

                    {!customOutput.results || customOutput.results.length === 0 ? (
                      <EmptyState title="No per-call results" />
                    ) : (
                      <div className="max-h-[300px] overflow-y-auto">
                        <table className="w-full text-xs text-left border-collapse">
                          <thead>
                            <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-semibold">
                              <th className="py-2 px-3">VCN</th>
                              <th className="py-2 px-3">Vessel Name</th>
                              <th className="py-2 px-3 text-right">Duration</th>
                              <th className="py-2 px-3 text-center">Status</th>
                              <th className="py-2 px-3 text-center">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[var(--color-border)]">
                            {customOutput.results.map((r, idx: number) => (
                              <tr key={idx} className="hover:bg-[var(--color-surface-muted)]">
                                <td className="py-1.5 px-3 font-semibold text-[var(--color-text-primary)] font-mono">{r.vcn}</td>
                                <td className="py-1.5 px-3 text-[var(--color-text-secondary)]">{r.vessel_name || '—'}</td>
                                <td className="py-1.5 px-3 text-right font-mono font-medium text-[var(--color-text-primary)]">
                                  {r.status === 'AVAILABLE' ? fmtHours(r.duration_hours) : '—'}
                                </td>
                                <td className="py-1.5 px-3 text-center">
                                  <StatusBadge tone={r.status === 'AVAILABLE' ? 'good' : 'neutral'} label={r.status} />
                                </td>
                                <td className="py-1.5 px-3 text-center">
                                  <Link
                                    href={`/vessel-journey?vcn=${r.vcn}`}
                                    className="text-[var(--color-accent)] hover:underline font-semibold text-[11px]"
                                  >
                                    Drill down
                                  </Link>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Card>
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
        <div className="flex-1 flex items-center justify-center bg-[var(--color-bg)]">
          <LoadingState label="Loading Time & Motion Explorer…" />
        </div>
      }
    >
      <TimeAndMotionContent />
    </React.Suspense>
  )
}
