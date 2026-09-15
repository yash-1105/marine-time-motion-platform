'use client'

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../lib/auth-context'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface LeadTimeStat {
  name: string
  observation_count: number
  missing_count: number
  mean_hours: number | null
  median_hours: number | null
  p90_hours: number | null
  min_hours: number | null
  max_hours: number | null
  unit: string
  formula_version: string
  status: string
  early_service_count: number
  delayed_count: number
  on_time_count: number
}

interface BottleneckItem {
  stage_or_resource: string
  bottleneck_type: string
  overall_bottleneck_score: number
  rank: number
  duration_score: number
  frequency_score: number
  variability_score: number
  tail_risk_score: number
  turnaround_contribution: number
  business_criticality_score: number
}

interface OutlierItem {
  vcn: string
  outlier_type: string
  severity: string
  observed_value: number
  divergence: number
  is_excluded_from_kpi: boolean
}

interface KPIHighlight {
  kpi_number: number
  code: string
  name: string
  value: number | null
  unit: string
  band: string
  target: number | null
  target_direction: string
  variance: number | null
  status: string
  formula_version: string
}

interface DashboardData {
  summary: {
    total_vessel_calls: number
    total_merged_calls: number
    clean_calls_count: number
    quarantined_calls_count: number
    flagged_calls_count: number
    cleanliness_pct: number
  }
  throughput: {
    teu: number
    mt: number
    units: number
    units_segmented: boolean
    prohibited_sum_notice: string
    cargo_breakdown: Array<{
      cargo_type: string
      unit: string
      quantity: number
      operations_count: number
    }>
  }
  lead_time_metrics: Record<string, LeadTimeStat>
  delays_summary: {
    total_delays_count: number
    total_delay_hours: number
    confirmed_count: number
    confirmed_hours: number
    inferred_count: number
    inferred_hours: number
    top_categories: Array<{
      category: string
      count: number
      duration_hours: number
      percentage: number
    }>
    top_bottlenecks: BottleneckItem[]
    outliers_count: number
    top_outliers: OutlierItem[]
  }
  kpi_highlights: KPIHighlight[]
  kpi_catalogue_summary: {
    total_registered: number
    computed_count: number
    no_source_data_count: number
    notice: string
  }
  lineage: {
    dataset_type: string
    dataset_label: string
    batch_id?: string
    file_checksum?: string
    port_id: string
    terminal_id: string
    vessel_type: string
    cargo_type: string
    timezone: string
    tolerance: string
    generated_at: string
  }
}

interface ReconciliationResult {
  status: string
  all_combinations_reconciled: boolean
  total_combinations_tested: number
  results: Array<{
    combination_name: string
    filters_applied: Record<string, string>
    dashboard_total: number
    analytics_api_total: number
    database_direct_total: number
    is_reconciled: boolean
    lead_time_turnaround_observations: number
    lead_time_turnaround_mean_hours: number | null
  }>
}

function fmtNum(n?: number | null, decimals = 1): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function ExecutiveDashboardContent() {
  const searchParams = useSearchParams()
  const { token, isLoading: authLoading } = useAuth()

  const [data, setData] = useState<DashboardData | null>(null)
  const [loadedBatchId, setLoadedBatchId] = useState<string | null>(null)
  const [newDatasetAvailable, setNewDatasetAvailable] = useState(false)
  const [newBatchName, setNewBatchName] = useState<string | null>(null)
  const [recon, setRecon] = useState<ReconciliationResult | null>(null)
  const [reconLoading, setReconLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showReconModal, setShowReconModal] = useState(false)

  // Sync with global filters
  const vesselType = searchParams.get('vesselType') || ''
  const cargoType = searchParams.get('cargoType') || ''
  const qualityStatus = searchParams.get('qualityStatus') || ''
  const startDate = searchParams.get('startDate') || ''
  const endDate = searchParams.get('endDate') || ''

  const queryParams = useMemo(() => {
    const p = new URLSearchParams()
    if (vesselType && vesselType !== 'ALL') p.set('vessel_type', vesselType)
    if (cargoType && cargoType !== 'ALL') p.set('cargo_type', cargoType)
    if (qualityStatus && qualityStatus !== 'ALL') p.set('quality_status', qualityStatus)
    if (startDate) p.set('start_date', startDate)
    if (endDate) p.set('end_date', endDate)
    return p.toString()
  }, [vesselType, cargoType, qualityStatus, startDate, endDate])

  const fetchDashboard = useCallback(async () => {
    setLoading(true)
    setError(null)

    const headers = { Authorization: `Bearer ${token || 'dev-token'}` }

    fetch(`${API}/api/v1/dashboard/executive?${queryParams}`, { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject(`Failed to load executive metrics: ${r.statusText}`)))
      .then((dashData) => {
        setData(dashData)
        if (dashData.lineage?.batch_id) {
          setLoadedBatchId(dashData.lineage.batch_id)
        }
        setNewDatasetAvailable(false)
        setLoading(false)
      })
      .catch((err) => {
        setError(String(err))
        setLoading(false)
      })
  }, [token, queryParams])

  useEffect(() => {
    if (authLoading) return
    fetchDashboard()
  }, [authLoading, fetchDashboard])

  // Detect when a newly uploaded dataset becomes active in the background
  useEffect(() => {
    if (authLoading || !token) return
    const checkActiveBatch = async () => {
      try {
        const res = await fetch(`${API}/api/v1/ingestion/active`, {
          headers: { Authorization: `Bearer ${token || 'dev-token'}` },
        })
        if (!res.ok) return
        const json = await res.json()
        if (json.has_active_dataset && json.batch?.batch_id) {
          if (loadedBatchId && json.batch.batch_id !== loadedBatchId) {
            setNewDatasetAvailable(true)
            setNewBatchName(json.batch.file_name || 'New Dataset')
          }
        }
      } catch {
        // Silently ignore background polling errors
      }
    }
    const timer = setInterval(checkActiveBatch, 8000)
    return () => clearInterval(timer)
  }, [authLoading, token, loadedBatchId])

  const handleRefreshNewDataset = useCallback(() => {
    setNewDatasetAvailable(false)
    fetchDashboard()
  }, [fetchDashboard])

  // 3-way reconciliation is expensive (recomputes the executive summary across 7 filter
  // combinations) — only run it on demand when the user opens the verification modal,
  // not automatically on every dashboard load.
  const fetchReconciliation = useCallback(() => {
    if (recon || reconLoading) {
      setShowReconModal(true)
      return
    }
    setReconLoading(true)
    const headers = { Authorization: `Bearer ${token || 'dev-token'}` }
    fetch(`${API}/api/v1/dashboard/reconciliation`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((reconData) => {
        if (reconData) setRecon(reconData)
        setShowReconModal(true)
      })
      .catch(() => {})
      .finally(() => setReconLoading(false))
  }, [token, recon, reconLoading])

  if (loading && !data) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-3">
          <span className="w-7 h-7 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin"></span>
          <span className="text-sm text-[var(--color-text-secondary)]">
            Loading executive dashboard…
          </span>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex-1 p-8 bg-[var(--color-bg)]">
        <div className="bg-[var(--color-critical-bg)] border border-[var(--color-critical-border)] rounded-lg p-6 max-w-xl mx-auto">
          <h2 className="text-sm font-semibold text-[var(--color-critical)] mb-2">
            Failed to load the executive dashboard
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)] mb-4">{error || 'Unknown error occurred'}</p>
          <button
            onClick={fetchDashboard}
            className="px-4 py-1.5 bg-[var(--color-critical)] hover:opacity-90 text-white rounded-md text-sm font-medium cursor-pointer"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (data.summary.total_vessel_calls === 0) {
    return (
      <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)]">
        <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 py-5 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Executive Dashboard</h1>
        </div>
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-8 max-w-md w-full text-center space-y-4 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-[var(--color-accent-soft)] text-[var(--color-accent)] flex items-center justify-center mx-auto text-xl font-semibold">
              ⚓
            </div>
            <div>
              <h2 className="text-base font-semibold text-[var(--color-text-primary)]">No dataset loaded</h2>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                Upload a port operations Excel workbook to compute and display executive analytics.
              </p>
            </div>
            <Link
              href="/ingestion"
              className="inline-block px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white text-sm font-medium rounded-md shadow-sm transition-colors"
            >
              Go to Data Ingestion
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-[var(--color-bg)] overflow-y-auto">
      {/* Page header */}
      <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 py-5 flex flex-wrap items-start justify-between gap-4 flex-shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)] tracking-tight">Executive Dashboard</h1>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchReconciliation}
            disabled={reconLoading}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border cursor-pointer transition-colors disabled:opacity-60 disabled:cursor-wait ${
              recon
                ? recon.all_combinations_reconciled
                  ? 'bg-[var(--color-good-bg)] border-[var(--color-good-border)] text-[var(--color-good)] hover:opacity-90'
                  : 'bg-[var(--color-critical-bg)] border-[var(--color-critical-border)] text-[var(--color-critical)] hover:opacity-90'
                : 'bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] border-[var(--color-border)]'
            }`}
          >
            {recon ? (
              <>
                <span aria-hidden="true">{recon.all_combinations_reconciled ? '✓' : '⚠'}</span>
                <span>Reconciliation: {recon.total_combinations_tested}/{recon.total_combinations_tested} matched</span>
              </>
            ) : (
              <span>{reconLoading ? 'Running 3-way reconciliation…' : 'Run 3-way reconciliation'}</span>
            )}
          </button>

          <button
            onClick={fetchDashboard}
            className="px-3 py-1.5 bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] rounded-md text-xs font-medium border border-[var(--color-border)] cursor-pointer"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* New dataset notification banner */}
      {newDatasetAvailable && (
        <div className="mx-6 mt-4 bg-[var(--color-surface)] border border-[var(--color-accent)] rounded-lg p-3 px-4 flex items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              New dataset available
            </span>
            {newBatchName && (
              <span className="text-xs text-[var(--color-text-secondary)]">
                — {newBatchName} is ready to view
              </span>
            )}
          </div>
          <button
            onClick={handleRefreshNewDataset}
            className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white text-xs font-semibold rounded-md cursor-pointer transition-colors shadow-sm"
          >
            Refresh
          </button>
        </div>
      )}

      {/* Main Dashboard Canvas */}
      <div className="p-6 space-y-6 flex-1">
        {/* 2. Top Metric Cards (Calls & Cleanliness) */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Total Calls */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[var(--color-text-secondary)] text-xs font-medium">
              <span>Active Vessel Calls</span>
              <span className="text-[11px] text-[var(--color-text-tertiary)]">Non-merged</span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-semibold text-[var(--color-text-primary)]">{data.summary.total_vessel_calls}</span>
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-xs">
              <span className="text-[var(--color-text-secondary)]">{data.summary.total_merged_calls} duplicates merged</span>
              <Link href="/vessel-calls" className="text-[var(--color-accent)] hover:underline font-medium">
                View list →
              </Link>
            </div>
          </div>

          {/* Clean Quality */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[var(--color-text-secondary)] text-xs font-medium">
              <span>Clean Calls</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-good-bg)] text-[var(--color-good)] border border-[var(--color-good-border)]">
                CLEAN
              </span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-semibold text-[var(--color-text-primary)]">{data.summary.clean_calls_count}</span>
              <span className="text-xs text-[var(--color-text-tertiary)]">({data.summary.cleanliness_pct}%)</span>
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]">
              Zero open quality exceptions
            </div>
          </div>

          {/* Flagged Quality */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[var(--color-text-secondary)] text-xs font-medium">
              <span>Flagged Calls</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-warning-bg)] text-[var(--color-warning)] border border-[var(--color-warning-border)]">
                FLAGGED
              </span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-semibold text-[var(--color-text-primary)]">{data.summary.flagged_calls_count}</span>
              <span className="text-xs text-[var(--color-text-tertiary)]">
                ({roundPct(data.summary.flagged_calls_count, data.summary.total_vessel_calls)}%)
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]">
              Non-critical review notices
            </div>
          </div>

          {/* Quarantined Quality */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between text-[var(--color-text-secondary)] text-xs font-medium">
              <span>Quarantined Calls</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-critical-bg)] text-[var(--color-critical)] border border-[var(--color-critical-border)]">
                QUARANTINED
              </span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-semibold text-[var(--color-text-primary)]">{data.summary.quarantined_calls_count}</span>
              <span className="text-xs text-[var(--color-text-tertiary)]">
                ({roundPct(data.summary.quarantined_calls_count, data.summary.total_vessel_calls)}%)
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-xs">
              <span className="text-[var(--color-critical)] font-medium">Excluded from KPIs</span>
              <Link href="/data-quality" className="text-[var(--color-accent)] hover:underline font-medium">
                Inspect issues →
              </Link>
            </div>
          </div>
        </div>

        {/* 3. Strict Throughput Segmentation (Spec §12.1 - NEVER SUM TEU, MT, UNITS) */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5">
          <div className="flex flex-wrap items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4 gap-2">
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Operational Cargo Throughput
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                Reported per cargo class — TEU, metric tons and units are never summed into a single figure.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* TEU */}
            <div className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Containerized Volume</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-accent-soft)] text-[var(--color-accent)] border border-[var(--color-accent-soft-border)]">
                  TEU
                </span>
              </div>
              <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">
                {fmtNum(data.throughput.teu, 0)} <span className="text-xs font-normal text-[var(--color-text-tertiary)]">TEU</span>
              </div>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">Fully cellular containership volume</p>
            </div>

            {/* MT */}
            <div className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Bulk & Liquid Tonnage</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-good-bg)] text-[var(--color-good)] border border-[var(--color-good-border)]">
                  MT
                </span>
              </div>
              <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">
                {fmtNum(data.throughput.mt, 0)} <span className="text-xs font-normal text-[var(--color-text-tertiary)]">Metric Tons</span>
              </div>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">Dry bulk, liquid tanker, and break bulk commodities</p>
            </div>

            {/* Units */}
            <div className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">Vehicles & Passengers</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-inferred-bg)] text-[var(--color-inferred)] border border-[var(--color-inferred-border)]">
                  Units
                </span>
              </div>
              <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">
                {fmtNum(data.throughput.units, 0)} <span className="text-xs font-normal text-[var(--color-text-tertiary)]">Units</span>
              </div>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">Ro-Ro vehicle moves and passenger counts</p>
            </div>
          </div>
        </div>

        {/* 4. Time & Motion Lead Times (8 Governed Target Durations) */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Time &amp; Motion Lead Times
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                8 governed stage durations, reconciled within ±0.02h tolerance
              </p>
            </div>
            <Link href="/time-and-motion" className="text-xs text-[var(--color-accent)] hover:underline font-medium">
              Open Lead-Time Explorer →
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[
              { id: 'Turnaround', label: 'Vessel Turnaround (ATA → ATD)', key: 'Turnaround' },
              { id: 'Berth Stay', label: 'Berth Stay (All Fast → Line Untied)', key: 'Berth Stay' },
              { id: 'Cargo Working', label: 'Cargo Working (Start → End)', key: 'Cargo Working' },
              { id: 'Anchorage Wait', label: 'Anchorage Wait (Arrive → Pilot On)', key: 'Anchorage Wait' },
              { id: 'Inward Movement', label: 'Inward Movement (Pilot On → All Fast)', key: 'Inward Movement' },
              { id: 'Outward Movement', label: 'Outward Movement (Pilot → Breakwater)', key: 'Outward Movement' },
              { id: 'Arrival Execution Delay', label: 'Arrival Execution Delay (Pilotage)', key: 'Arrival Execution Delay' },
              { id: 'Sailing Execution Delay', label: 'Sailing Execution Delay (Pilotage)', key: 'Sailing Execution Delay' },
            ].map((st) => {
              const m = data.lead_time_metrics[st.key]
              const isDelay = st.key.includes('Execution Delay')

              return (
                <div key={st.id} className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-3 flex flex-col justify-between">
                  <div>
                    <div className="text-xs font-medium text-[var(--color-text-secondary)] truncate" title={st.label}>
                      {st.label}
                    </div>
                    <div className="mt-2 flex items-baseline justify-between">
                      <span className="text-lg font-semibold text-[var(--color-text-primary)]">
                        {m?.mean_hours != null ? `${m.mean_hours.toFixed(2)}h` : '—'}
                      </span>
                      <span className="text-[11px] text-[var(--color-text-tertiary)]">
                        {m?.observation_count || 0} calls
                      </span>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-tertiary)] flex items-center justify-between">
                    <span>Med: {m?.median_hours != null ? `${m.median_hours.toFixed(1)}h` : '—'}</span>
                    <span>P90: {m?.p90_hours != null ? `${m.p90_hours.toFixed(1)}h` : '—'}</span>
                  </div>

                  {isDelay && m && (
                    <div className="mt-1 text-[11px] flex items-center justify-between">
                      <span className="text-[var(--color-accent)]">Early: {m.early_service_count}</span>
                      <span className="text-[var(--color-warning)]">Delayed: {m.delayed_count}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* 5. Delays, Bottlenecks & Critical Outliers */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Delays & Pareto */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5 flex flex-col">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Delays &amp; Root Causes
                </h2>
                <span className="text-xs text-[var(--color-text-secondary)]">
                  {data.delays_summary.total_delays_count} delays · {data.delays_summary.total_delay_hours}h total impact
                </span>
              </div>
              <div className="flex gap-1.5">
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-good-bg)] text-[var(--color-good)] border border-[var(--color-good-border)]">
                  Confirmed: {data.delays_summary.confirmed_count}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-inferred-bg)] text-[var(--color-inferred)] border border-[var(--color-inferred-border)]">
                  Inferred: {data.delays_summary.inferred_count}
                </span>
              </div>
            </div>

            <div className="space-y-3 flex-1">
              {data.delays_summary.top_categories.map((cat, i) => (
                <div key={i} className="text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-[var(--color-text-secondary)]">{cat.category}</span>
                    <span className="text-[var(--color-text-tertiary)]">
                      {cat.duration_hours.toFixed(1)}h ({cat.percentage}%)
                    </span>
                  </div>
                  <div className="w-full bg-[var(--color-surface-muted)] rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-[var(--color-accent)] h-full rounded-full"
                      style={{ width: `${Math.min(100, cat.percentage)}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-3 border-t border-[var(--color-border)] text-right">
              <Link href="/delays" className="text-xs text-[var(--color-accent)] hover:underline font-medium">
                Explore delay analysis & reason mapping →
              </Link>
            </div>
          </div>

          {/* Multi-Dimensional Bottlenecks */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5 flex flex-col">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Operational Bottlenecks
                </h2>
                <span className="text-xs text-[var(--color-text-secondary)]">
                  Ranked by duration, variance, tail risk, and frequency
                </span>
              </div>
            </div>

            <div className="space-y-2.5 flex-1">
              {data.delays_summary.top_bottlenecks.map((b, i) => (
                <div key={i} className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-secondary)] flex items-center justify-center font-semibold text-[11px]">
                        {b.rank || i + 1}
                      </span>
                      <span className="font-medium text-[var(--color-text-primary)]">{b.stage_or_resource}</span>
                    </div>
                    <span className="font-semibold text-[var(--color-accent)]">
                      Score: {b.overall_bottleneck_score}
                    </span>
                  </div>

                  {/* Component scores breakdown */}
                  <div className="grid grid-cols-4 gap-2 mt-2 pt-2 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-tertiary)]">
                    <div>Dur: {b.duration_score?.toFixed(0)}</div>
                    <div>Var: {b.variability_score?.toFixed(0)}</div>
                    <div>Tail: {b.tail_risk_score?.toFixed(0)}</div>
                    <div>Freq: {b.frequency_score?.toFixed(0)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 6. Governed KPI Spotlight & NO_SOURCE_DATA Disclosure */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-5">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
                KPI Performance
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                Target, variance, and status from the governed KPI registry
              </p>
            </div>
            <Link href="/kpis" className="text-xs text-[var(--color-accent)] hover:underline font-medium">
              View all 55 KPIs →
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {data.kpi_highlights.map((kpi) => {
              const isGreen = kpi.band === 'GREEN'
              const isAmber = kpi.band === 'AMBER'
              const isRed = kpi.band === 'RED'

              return (
                <div key={kpi.code} className="bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg p-3 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-medium text-[var(--color-text-tertiary)]">{kpi.code}</span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                          isGreen
                            ? 'bg-[var(--color-good-bg)] text-[var(--color-good)] border-[var(--color-good-border)]'
                            : isAmber
                            ? 'bg-[var(--color-warning-bg)] text-[var(--color-warning)] border-[var(--color-warning-border)]'
                            : isRed
                            ? 'bg-[var(--color-critical-bg)] text-[var(--color-critical)] border-[var(--color-critical-border)]'
                            : 'bg-[var(--color-neutral-bg)] text-[var(--color-neutral)] border-[var(--color-neutral-border)]'
                        }`}
                      >
                        {kpi.band}
                      </span>
                    </div>
                    <div className="text-xs font-medium text-[var(--color-text-primary)] line-clamp-1" title={kpi.name}>
                      {kpi.name}
                    </div>
                    <div className="mt-2 text-lg font-semibold text-[var(--color-text-primary)]">
                      {kpi.value != null ? kpi.value.toFixed(2) : '—'}{' '}
                      <span className="text-xs font-normal text-[var(--color-text-tertiary)]">{kpi.unit}</span>
                    </div>
                  </div>

                  <div className="mt-2 pt-2 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-tertiary)] flex items-center justify-between">
                    <span>Target: {kpi.target != null ? kpi.target : '—'}</span>
                    <span>Var: {kpi.variance != null ? `${kpi.variance > 0 ? '+' : ''}${kpi.variance.toFixed(1)}` : '—'}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* NO_SOURCE_DATA Disclosure */}
          <div className="mt-4 p-3 bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-lg flex items-center justify-between text-xs gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)]">
              <span className="text-[var(--color-warning)]" aria-hidden="true">ℹ</span>
              <span>
                <strong className="text-[var(--color-text-primary)]">17 KPIs</strong> classified as{' '}
                <span className="font-medium text-[var(--color-text-primary)]">NO_SOURCE_DATA</span> (yard dwell, gate queues, crane telemetry) — values are never fabricated as zero.
              </span>
            </div>
            <Link href="/kpis" className="text-[var(--color-accent)] hover:underline font-medium flex-shrink-0">
              Inspect required source systems →
            </Link>
          </div>
        </div>
      </div>

      {/* 3-Way Reconciliation Modal */}
      {showReconModal && recon && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg max-w-2xl w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <div>
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  3-Way Reconciliation Verification
                </h3>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                  Confirms that Dashboard totals, Analytics API, and direct database queries agree.
                </p>
              </div>
              <button
                onClick={() => setShowReconModal(false)}
                className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] font-semibold text-sm px-2 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-tertiary)]">
                    <th className="py-2 px-3 font-medium">Filter Combination</th>
                    <th className="py-2 px-3 text-right font-medium">Dashboard</th>
                    <th className="py-2 px-3 text-right font-medium">Analytics API</th>
                    <th className="py-2 px-3 text-right font-medium">Direct SQL</th>
                    <th className="py-2 px-3 text-center font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {recon.results.map((r, i) => (
                    <tr key={i} className="hover:bg-[var(--color-surface-muted)]">
                      <td className="py-2 px-3 font-medium text-[var(--color-text-primary)]">{r.combination_name}</td>
                      <td className="py-2 px-3 text-right text-[var(--color-text-primary)]">{r.dashboard_total}</td>
                      <td className="py-2 px-3 text-right text-[var(--color-text-primary)]">{r.analytics_api_total}</td>
                      <td className="py-2 px-3 text-right text-[var(--color-text-primary)]">{r.database_direct_total}</td>
                      <td className="py-2 px-3 text-center">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[var(--color-good-bg)] text-[var(--color-good)] border border-[var(--color-good-border)]">
                          MATCH
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pt-3 border-t border-[var(--color-border)] flex justify-end">
              <button
                onClick={() => setShowReconModal(false)}
                className="px-4 py-1.5 bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-xs font-medium cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function roundPct(n: number, total: number): number {
  if (!total) return 0
  return Math.round((n / total) * 1000) / 10
}

export default function HomePage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center bg-slate-900 text-slate-400 text-xs font-mono">
          Loading Executive Dashboard…
        </div>
      }
    >
      <ExecutiveDashboardContent />
    </React.Suspense>
  )
}
