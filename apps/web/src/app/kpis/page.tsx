'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'
import {
  PageHeader,
  SectionHeader,
  Card,
  KpiCard,
  StatusBadge,
  statusToTone,
  EmptyState,
  LoadingState,
  ErrorState,
  type StatusTone,
} from '@/components/ui'

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

/** Maps a governance band (GREEN/AMBER/RED/GRAY) to a StatusBadge tone. Distinct from statusToTone, which maps lifecycle status. */
function bandToTone(band?: string): StatusTone {
  switch (band) {
    case 'GREEN':
      return 'good'
    case 'AMBER':
      return 'warning'
    case 'RED':
      return 'critical'
    default:
      return 'neutral'
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
  const { token, can, isLoading: authLoading } = useAuth()
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
    if (authLoading) return
    fetchScorecard()
  }, [authLoading, fetchScorecard])

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
    <div className="min-h-full bg-[var(--color-bg)]">
      <PageHeader
        title="Governed KPI Engine & Scorecard"
        description="Complete catalogue of all 55 governed port operational KPIs (spec §11). Explicit status, lineage, and no fabricated values."
        actions={
          <>
            <label className="flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] bg-[var(--color-surface)] px-3 py-1.5 rounded-md border border-[var(--color-border)] cursor-pointer">
              <input
                type="checkbox"
                checked={includeAliases}
                onChange={(e) => setIncludeAliases(e.target.checked)}
                className="rounded border-[var(--color-border-strong)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
              />
              Show Alias Concepts (11/53, 14/51)
            </label>
            <button
              onClick={() => fetchScorecard()}
              className="text-xs font-semibold px-3 py-2 bg-[var(--color-accent)] text-white rounded-md hover:bg-[var(--color-accent-hover)] transition cursor-pointer"
            >
              Refresh Scorecard
            </button>
          </>
        }
      />

      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Banner / Feedback Message */}
        {actionMessage && (
          <div
            className={`p-3 rounded-md text-sm border flex justify-between items-center gap-3 ${
              actionMessage.type === 'success'
                ? 'bg-[var(--color-good-bg)] text-[var(--color-good)] border-[var(--color-good-border)]'
                : 'bg-[var(--color-critical-bg)] text-[var(--color-critical)] border-[var(--color-critical-border)]'
            }`}
          >
            <span>{actionMessage.text}</span>
            <button
              onClick={() => setActionMessage(null)}
              className="font-bold text-current cursor-pointer"
              aria-label="Dismiss message"
            >
              ×
            </button>
          </div>
        )}

        {/* High-level Governance Summary */}
        {scorecard && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <KpiCard
              label="Governed Registry"
              value={scorecard.total_kpis}
              unit="KPIs"
              context="Exact spec numbering KPI-01 to KPI-55"
            />
            <KpiCard
              label="Computed Population"
              value={scorecard.computed}
              unit="active"
              tone="good"
              status="COMPUTED"
              context="Evaluated against canonical records"
            />
            <KpiCard
              label="No Connected Source"
              value={scorecard.no_source_data}
              unit="registered"
              tone="neutral"
              status="NO_SOURCE_DATA"
              context="Yard/gate/maintenance (no fake zeroes)"
            />
            <KpiCard
              label="Unavailable In Period"
              value={scorecard.unavailable}
              unit="missing"
              tone="critical"
              status="UNAVAILABLE"
              context="Missing inputs named explicitly"
            />
          </div>
        )}

        {/* Category Tabs */}
        {scorecard && (
          <div className="flex border-b border-[var(--color-border)] overflow-x-auto gap-1 text-sm font-medium">
            <button
              onClick={() => setActiveTab('ALL')}
              className={`py-2 px-3 border-b-2 whitespace-nowrap cursor-pointer transition ${
                activeTab === 'ALL'
                  ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-semibold'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              All Categories
            </button>
            {categoryNames.map((cat) => (
              <button
                key={cat}
                onClick={() => setActiveTab(cat)}
                className={`py-2 px-3 border-b-2 whitespace-nowrap cursor-pointer transition ${
                  activeTab === cat
                    ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-semibold'
                    : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                }`}
              >
                {cat} ({scorecard?.categories[cat].length || 0})
              </button>
            ))}
          </div>
        )}

        {/* KPI Cards / Tables */}
        {loading ? (
          <LoadingState label="Loading governed KPI metrics…" />
        ) : scorecard ? (
          <div className="space-y-6">
            {categoryNames
              .filter((cat) => activeTab === 'ALL' || activeTab === cat)
              .map((cat) => {
                const items = scorecard.categories[cat]
                return (
                  <Card key={cat} padded={false} className="overflow-hidden">
                    <div className="px-5 py-3.5 bg-[var(--color-surface-muted)] border-b border-[var(--color-border)] flex justify-between items-center">
                      <h2 className="text-sm font-bold text-[var(--color-text-primary)] uppercase tracking-wide">{cat}</h2>
                      <span className="text-xs font-medium text-[var(--color-text-secondary)]">{items.length} metrics</span>
                    </div>
                    <div className="divide-y divide-[var(--color-border)]">
                      {items.map((item) => (
                        <div
                          key={item.code}
                          className="px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-[var(--color-surface-muted)] transition"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-mono text-xs font-bold text-[var(--color-accent)] bg-[var(--color-accent-soft)] px-2 py-0.5 rounded border border-[var(--color-accent-soft-border)]">
                                {item.code}
                              </span>
                              <span className="text-sm font-semibold text-[var(--color-text-primary)]">{item.name}</span>
                              {!item.is_primary && (
                                <button
                                  onClick={() => handleSwapPrimary(item)}
                                  title="Click to designate as primary"
                                  className="text-xs font-semibold px-2 py-0.5 rounded bg-[var(--color-warning-bg)] text-[var(--color-warning)] border border-[var(--color-warning-border)] hover:opacity-80 transition cursor-pointer"
                                >
                                  Alias (Make Primary)
                                </button>
                              )}
                            </div>
                            <div className="text-xs text-[var(--color-text-secondary)]">
                              Unit: <span className="font-medium text-[var(--color-text-primary)]">{item.unit}</span>
                              {item.target !== undefined && item.target !== null && (
                                <span className="ml-3">
                                  Target: <span className="font-medium text-[var(--color-text-primary)]">{item.target}</span> (
                                  {item.target_direction === 'HIGHER_IS_BETTER' ? 'Higher is better' : 'Lower is better'})
                                </span>
                              )}
                            </div>
                            {item.status === 'NO_SOURCE_DATA' && (
                              <div className="text-xs text-[var(--color-text-tertiary)] italic">
                                Requires: {item.required_source_systems.join(', ') || 'Connected sensors/gate systems'}
                              </div>
                            )}
                          </div>

                          <div className="flex items-center gap-4 self-start sm:self-center">
                            {item.status === 'COMPUTED' ? (
                              <div className="text-right">
                                <div className="text-base font-bold text-[var(--color-text-primary)]">
                                  {fmtValue(item.value, item.unit)}
                                </div>
                                <StatusBadge
                                  label={item.band || 'BAND UNSET'}
                                  tone={bandToTone(item.band)}
                                  showGlyph={false}
                                  className="mt-0.5"
                                />
                              </div>
                            ) : (
                              <StatusBadge status={item.status} tone={statusToTone(item.status)} />
                            )}

                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleSelectKPI(item)}
                                className="text-xs font-medium px-2.5 py-1.5 text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)] rounded transition cursor-pointer"
                              >
                                Lineage & Trends
                              </button>
                              {item.status === 'COMPUTED' && can('recalculate') && (
                                <button
                                  onClick={() => {
                                    setSelectedKPI(item)
                                    setRecalcModalOpen(true)
                                  }}
                                  className="text-xs font-medium px-2.5 py-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] rounded transition cursor-pointer"
                                >
                                  Recalculate
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )
              })}
          </div>
        ) : (
          <ErrorState
            title="Governed KPI scorecard unavailable"
            description="The scorecard could not be loaded. Check the connection to the KPI engine and try again."
            onRetry={fetchScorecard}
          />
        )}
      </div>

      {/* Recalculate Modal */}
      {recalcModalOpen && selectedKPI && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="max-w-md w-full space-y-4">
            <div>
              <h3 className="text-lg font-bold text-[var(--color-text-primary)]">Permissioned Recalculation</h3>
              <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                Recalculating {selectedKPI.code} ({selectedKPI.name}). An entry will be permanently logged in audit.audit_event.
              </p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[var(--color-text-primary)] uppercase mb-1">
                Audit Reason / Justification <span className="text-[var(--color-critical)]">*</span>
              </label>
              <textarea
                value={recalcReason}
                onChange={(e) => setRecalcReason(e.target.value)}
                placeholder="e.g. Verified data correction or periodic governance recalculation"
                rows={3}
                className="w-full text-xs p-2.5 border border-[var(--color-border)] rounded focus:ring-1 focus:ring-[var(--color-accent)] outline-none bg-[var(--color-surface)] text-[var(--color-text-primary)]"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border)]">
              <button
                onClick={() => setRecalcModalOpen(false)}
                className="text-xs px-3 py-1.5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleRecalculate}
                disabled={!recalcReason.trim()}
                className="text-xs font-semibold px-3 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 text-white rounded transition cursor-pointer disabled:cursor-not-allowed"
              >
                Execute Recalculation
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* Detail & Trends Drawer */}
      {selectedKPI && (
        <div className="max-w-7xl mx-auto px-6 pb-6">
          <Card className="space-y-4">
            <div className="flex justify-between items-start border-b border-[var(--color-border)] pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-[var(--color-accent)]">{selectedKPI.code}</span>
                  <h3 className="text-base font-bold text-[var(--color-text-primary)]">{selectedKPI.name}</h3>
                </div>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">Unit: {selectedKPI.unit}</p>
              </div>
              <button
                onClick={() => {
                  setSelectedKPI(null)
                  setKPITrends(null)
                  setKPIBenchmark(null)
                }}
                className="text-sm font-bold text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] cursor-pointer"
              >
                ✕ Close
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Trends */}
              <div>
                <SectionHeader
                  title="Trend & Direction"
                  action={
                    kpiTrends && (
                      <StatusBadge
                        label={kpiTrends.direction}
                        tone={
                          kpiTrends.direction === 'IMPROVING'
                            ? 'good'
                            : kpiTrends.direction === 'DETERIORATING'
                            ? 'critical'
                            : 'neutral'
                        }
                        showGlyph={false}
                      />
                    )
                  }
                />
                {kpiTrends ? (
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between text-[var(--color-text-secondary)]">
                      <span>Rolling 3-Period Average:</span>
                      <span className="font-semibold text-[var(--color-text-primary)]">
                        {fmtValue(kpiTrends.rolling_average_3p, selectedKPI.unit)}
                      </span>
                    </div>
                    {kpiTrends.delta !== null && (
                      <div className="flex justify-between text-[var(--color-text-secondary)]">
                        <span>Prior Period Delta:</span>
                        <span className="font-semibold text-[var(--color-text-primary)]">
                          {kpiTrends.delta && kpiTrends.delta > 0 ? `+${kpiTrends.delta}` : kpiTrends.delta}{' '}
                          {kpiTrends.percentage_change ? `(${kpiTrends.percentage_change}%)` : ''}
                        </span>
                      </div>
                    )}
                    <div className="pt-2 border-t border-[var(--color-border)] space-y-1.5">
                      <div className="font-semibold text-[var(--color-text-tertiary)] text-[11px] uppercase">
                        Recent Periods:
                      </div>
                      {kpiTrends.trend_points.map((tp, idx) => {
                        const maxVal = Math.max(
                          1,
                          ...kpiTrends.trend_points.map((p) => (typeof p.value === 'number' ? p.value : 0))
                        )
                        const pct = typeof tp.value === 'number' ? Math.max(4, (tp.value / maxVal) * 100) : 0
                        return (
                          <div key={idx} className="flex items-center gap-2">
                            <span className="w-20 shrink-0 text-[var(--color-text-secondary)]">{tp.period}</span>
                            <div className="flex-1 h-1.5 rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
                              {typeof tp.value === 'number' && (
                                <div
                                  className="h-full rounded-full bg-[var(--color-accent)]"
                                  style={{ width: `${pct}%` }}
                                />
                              )}
                            </div>
                            <span className="w-24 shrink-0 text-right font-mono font-medium text-[var(--color-text-primary)]">
                              {fmtValue(tp.value, selectedKPI.unit)}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-[var(--color-text-tertiary)]">Loading trend points…</p>
                )}
              </div>

              {/* Peer Port Benchmark */}
              <div>
                <SectionHeader title="Peer Port Benchmarks" />
                {kpiBenchmark ? (
                  kpiBenchmark.has_benchmarks ? (
                    <div className="space-y-2 text-xs">
                      {kpiBenchmark.benchmarks.map((b) => (
                        <div
                          key={b.id}
                          className="p-2 bg-[var(--color-surface-muted)] rounded border border-[var(--color-border)] space-y-1"
                        >
                          <div className="flex justify-between font-semibold text-[var(--color-text-primary)]">
                            <span>{b.peer_port}</span>
                            <span>{fmtValue(b.benchmark_value, selectedKPI.unit)}</span>
                          </div>
                          <div className="text-[11px] text-[var(--color-text-tertiary)]">
                            Source: {b.source || '—'} | Period: {b.period || '—'}
                          </div>
                          {b.notes && <div className="text-[11px] text-[var(--color-text-secondary)]">{b.notes}</div>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="No peer-port benchmark data configured."
                      description={kpiBenchmark.absent_notice}
                      className="py-6"
                    />
                  )
                ) : (
                  <p className="text-xs text-[var(--color-text-tertiary)]">Checking benchmarks…</p>
                )}
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
