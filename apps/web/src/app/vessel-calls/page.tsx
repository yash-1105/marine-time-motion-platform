'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth-context'
import { PageHeader, StatusBadge, EmptyState, ErrorState, LoadingState } from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface DurationTraceability {
  duration_hours: number | null
  status: string
  unavailable_reason?: string | null
  formula: string
  formula_version: string
  source_records: string[]
  filters: Record<string, unknown>
  exclusions: string[]
  dq_status: string
  start_time?: string | null
  end_time?: string | null
}

interface VesselCallRecord {
  id: string
  vessel_name: string
  vcn: string
  imo_number?: string | null
  vessel_type?: string | null
  cargo_type?: string | null
  vessel_size_teu?: number | null
  flag?: string | null
  tenant_id: string
  port_id?: string | null
  terminal_id?: string | null
  is_merged: boolean
  merged_into_id?: string | null
  journey_status: string
  journey_completeness_pct: number
  stages_available: number
  stages_total: number
  shifting_occurrences: number
  ata?: string | null
  atd?: string | null
  eta?: string | null
  turnaround_hours: number | null
  turnaround_status: string
  turnaround_unavailable_reason?: string | null
  anchorage_wait_hours: number | null
  berth_stay_hours: number | null
  inward_movement_hours: number | null
  cargo_working_hours: number | null
  outward_movement_hours: number | null
  arrival_execution_delay: number | null
  sailing_execution_delay: number | null
  delays_count: number
  total_delay_hours: number
  quality_status: 'CLEAN' | 'FLAGGED' | 'QUARANTINED'
  quality_score: number
  issue_count: number
  critical_issue_count: number
  durations_traceability: Record<string, DurationTraceability>
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return '—'
  const sign = h < 0 ? '-' : ''
  const abs = Math.abs(h)
  const hh = Math.floor(abs)
  const mm = Math.round((abs - hh) * 60)
  return `${sign}${hh}h ${mm.toString().padStart(2, '0')}m`
}

function fmtTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return d.toISOString().replace('T', ' ').substring(0, 16)
  } catch {
    return ts
  }
}

function VesselCallsContent() {
  const searchParams = useSearchParams()
  const { token } = useAuth()

  const [calls, setCalls] = useState<VesselCallRecord[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // Local table controls
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [sortBy, setSortBy] = useState<string>('vcn')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(25)
  const [showMerged, setShowMerged] = useState<boolean>(false)

  // Traceability Drawer state
  const [traceabilityTarget, setTraceabilityTarget] = useState<{
    call: VesselCallRecord
    metricName: string
    traceability: DurationTraceability
  } | null>(null)

  const getActiveAuthHeaders = useCallback((): HeadersInit => {
    const t = token || (typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null)
    return t ? { Authorization: `Bearer ${t}` } : {}
  }, [token])

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const headers = getActiveAuthHeaders()
      const params = new URLSearchParams()
      params.set('limit', '250')

      // Inherit global scope filters if set in URL
      const vType = searchParams.get('vesselType')
      if (vType) params.set('vessel_type', vType)

      const cType = searchParams.get('cargoType')
      if (cType) params.set('cargo_type', cType)

      const dq = searchParams.get('qualityStatus')
      if (dq) params.set('quality_status', dq)

      if (!showMerged) {
        params.set('is_merged', 'false')
      }

      const res = await fetch(`${API}/api/v1/operations/vessel-calls?${params.toString()}`, { headers })
      if (!res.ok) {
        throw new Error(`Failed to load vessel calls: ${res.statusText}`)
      }
      const data = await res.json()
      setCalls(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error loading vessel calls')
    } finally {
      setLoading(false)
    }
  }, [searchParams, showMerged, getActiveAuthHeaders])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Filtered & Sorted in-memory for instant responsive UI
  const filteredCalls = useMemo(() => {
    let result = [...calls]

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase().trim()
      result = result.filter(
        (c) =>
          c.vcn.toLowerCase().includes(q) ||
          c.vessel_name.toLowerCase().includes(q) ||
          (c.imo_number && c.imo_number.toLowerCase().includes(q))
      )
    }

    result.sort((a, b) => {
      let valA: unknown = a[sortBy as keyof VesselCallRecord]
      let valB: unknown = b[sortBy as keyof VesselCallRecord]

      if (valA === null || valA === undefined) valA = sortDir === 'asc' ? Infinity : -Infinity
      if (valB === null || valB === undefined) valB = sortDir === 'asc' ? Infinity : -Infinity

      if (typeof valA === 'string') {
        return sortDir === 'asc'
          ? (valA as string).localeCompare(valB as string)
          : (valB as string).localeCompare(valA as string)
      }
      if (typeof valA === 'number') {
        return sortDir === 'asc'
          ? (valA as number) - (valB as number)
          : (valB as number) - (valA as number)
      }
      return 0
    })

    return result
  }, [calls, searchTerm, sortBy, sortDir])

  // Pagination slice
  const paginatedCalls = useMemo(() => {
    const start = (page - 1) * pageSize
    return filteredCalls.slice(start, start + pageSize)
  }, [filteredCalls, page, pageSize])

  const totalPages = Math.ceil(filteredCalls.length / pageSize) || 1

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(field)
      setSortDir('asc')
    }
  }

  // Summary statistics from real data
  const stats = useMemo(() => {
    const active = calls.filter((c) => !c.is_merged)
    const quarantined = active.filter((c) => c.quality_status === 'QUARANTINED').length
    const withShift = active.filter((c) => c.shifting_occurrences > 0).length
    const earlyArrival = active.filter((c) => c.arrival_execution_delay !== null && c.arrival_execution_delay < 0).length
    const earlySailing = active.filter((c) => c.sailing_execution_delay !== null && c.sailing_execution_delay < 0).length

    return {
      total: active.length,
      quarantined,
      withShift,
      earlyArrival,
      earlySailing,
    }
  }, [calls])

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      {/* 1. Page Header & Real Operational KPI Pills */}
      <PageHeader
        title="Vessel Calls"
        meta={
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge label={`${filteredCalls.length} calls`} tone="neutral" showGlyph={false} />
            <StatusBadge label={`Active Base: ${stats.total}`} tone="neutral" showGlyph={false} />
            <StatusBadge label={`Shifting: ${stats.withShift}`} tone="warning" showGlyph={false} />
            <StatusBadge label={`Early Svc: ${stats.earlyArrival + stats.earlySailing}`} tone="good" showGlyph={false} />
            {stats.quarantined > 0 && (
              <StatusBadge label={`Quarantined: ${stats.quarantined}`} tone="critical" showGlyph={false} />
            )}
          </div>
        }
      />

      {/* 2. Search & Controls Bar */}
      <div className="bg-[var(--color-surface-muted)] border-b border-[var(--color-border)] px-6 py-2.5 flex items-center justify-between gap-4 flex-wrap flex-shrink-0">
        <div className="flex items-center gap-3 flex-1 min-w-[280px]">
          {/* Instant Search input */}
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              placeholder="Search by VCN, vessel name, IMO…"
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value)
                setPage(1)
              }}
              className="w-full text-xs bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md px-3 py-1.5 pl-8 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] text-[var(--color-text-primary)]"
            />
            <span className="absolute left-2.5 top-1.5 text-[var(--color-text-tertiary)] text-xs">🔍</span>
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-1.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-xs cursor-pointer"
              >
                ✕
              </button>
            )}
          </div>

          {/* Include Merged Records Toggle */}
          <label className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showMerged}
              onChange={(e) => {
                setShowMerged(e.target.checked)
                setPage(1)
              }}
              className="rounded border-[var(--color-border-strong)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
            />
            <span>Show Merged Duplicates</span>
          </label>
        </div>

        {/* Page size selector */}
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPage(1)
            }}
            className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] cursor-pointer"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
      </div>

      {/* 3. Main Data Table */}
      <div className="flex-1 overflow-auto bg-[var(--color-surface)]">
        {loading ? (
          <LoadingState label="Loading consolidated vessel calls and calculated lead times…" />
        ) : error ? (
          <ErrorState title="Error Loading Vessel Calls" description={error} onRetry={fetchData} />
        ) : paginatedCalls.length === 0 ? (
          <EmptyState
            title="No vessel calls found"
            description="No vessel calls match the current filters. Try adjusting search or filter criteria."
          />
        ) : (
          <table className="w-full border-collapse text-left text-xs" aria-label="Consolidated Vessel Calls Table">
            <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] sticky top-0 z-10 select-none">
              <tr>
                <th
                  onClick={() => handleSort('vcn')}
                  className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] cursor-pointer hover:text-[var(--color-accent)] whitespace-nowrap"
                >
                  VCN {sortBy === 'vcn' && (sortDir === 'asc' ? '▲' : '▼')}
                </th>
                <th
                  onClick={() => handleSort('vessel_name')}
                  className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] cursor-pointer hover:text-[var(--color-accent)]"
                >
                  Vessel Name &amp; IMO {sortBy === 'vessel_name' && (sortDir === 'asc' ? '▲' : '▼')}
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)]">
                  Type / Cargo
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)]">
                  Quality Status
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)]">
                  Journey
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)]">
                  Arrival (ATA)
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)]">
                  Departure (ATD)
                </th>
                <th
                  onClick={() => handleSort('turnaround_hours')}
                  className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-right cursor-pointer hover:text-[var(--color-accent)] whitespace-nowrap"
                  title="Click to sort. Click any cell to inspect mathematical formula and lineage."
                >
                  Turnaround {sortBy === 'turnaround_hours' && (sortDir === 'asc' ? '▲' : '▼')}
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-right whitespace-nowrap">
                  Anch. Wait
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-right whitespace-nowrap">
                  Berth Stay
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-right whitespace-nowrap">
                  Inward Mov.
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-right whitespace-nowrap">
                  Delays
                </th>
                <th className="px-3 py-2.5 font-semibold border-b border-[var(--color-border)] text-center">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
              {paginatedCalls.map((c, idx) => {
                const isQuarantined = c.quality_status === 'QUARANTINED'
                const isFlagged = c.quality_status === 'FLAGGED'

                return (
                  <tr
                    key={c.id}
                    className={`hover:bg-[var(--color-surface-muted)] transition-colors ${
                      isQuarantined ? 'bg-[var(--color-critical-bg)]/40' : idx % 2 === 1 ? 'bg-[var(--color-surface-muted)]/40' : ''
                    }`}
                  >
                    {/* VCN */}
                    <td className="px-3 py-2.5 font-mono font-semibold text-[var(--color-text-primary)] whitespace-nowrap">
                      <Link
                        href={`/vessel-journey?vcn=${c.vcn}`}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] hover:underline flex items-center gap-1.5"
                        title="Drill into Vessel Journey"
                      >
                        {c.vcn}
                        {c.is_merged && <StatusBadge label="MERGED" tone="neutral" showGlyph={false} />}
                      </Link>
                    </td>

                    {/* Vessel Name & IMO */}
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-[var(--color-text-primary)] truncate max-w-[180px]">{c.vessel_name}</div>
                      <div className="text-[10px] text-[var(--color-text-tertiary)] font-mono">
                        {c.imo_number ? `IMO: ${c.imo_number}` : 'IMO: —'}
                      </div>
                    </td>

                    {/* Type & Cargo */}
                    <td className="px-3 py-2.5 text-[var(--color-text-secondary)]">
                      <div>{c.vessel_type || '—'}</div>
                      <div className="text-[10px] text-[var(--color-text-tertiary)]">{c.cargo_type || '—'}</div>
                    </td>

                    {/* Quality Status Badge */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {isQuarantined ? (
                        <StatusBadge status="QUARANTINED" />
                      ) : isFlagged ? (
                        <StatusBadge status="FLAGGED" label={`Flagged (${c.issue_count})`} />
                      ) : (
                        <StatusBadge status="CLEAN" />
                      )}
                    </td>

                    {/* Journey Completeness */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-[var(--color-good)] h-1.5 rounded-full"
                            style={{ width: `${c.journey_completeness_pct}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-[var(--color-text-secondary)]">
                          {c.stages_available}/{c.stages_total}
                        </span>
                      </div>
                      {c.shifting_occurrences > 0 && (
                        <div className="text-[9px] text-[var(--color-warning)] font-semibold mt-0.5">
                          ⇄ {c.shifting_occurrences} shift
                        </div>
                      )}
                    </td>

                    {/* Arrival (ATA) */}
                    <td className="px-3 py-2.5 font-mono text-[11px] text-[var(--color-text-secondary)] whitespace-nowrap">
                      {fmtTimestamp(c.ata)}
                    </td>

                    {/* Departure (ATD) */}
                    <td className="px-3 py-2.5 font-mono text-[11px] text-[var(--color-text-secondary)] whitespace-nowrap">
                      {fmtTimestamp(c.atd)}
                    </td>

                    {/* Turnaround Duration (Clickable for Traceability) */}
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {c.turnaround_status === 'AVAILABLE' && c.turnaround_hours !== null ? (
                        <button
                          onClick={() =>
                            setTraceabilityTarget({
                              call: c,
                              metricName: 'Turnaround',
                              traceability: c.durations_traceability['Turnaround'],
                            })
                          }
                          className="font-semibold text-[var(--color-text-primary)] hover:text-[var(--color-accent)] hover:underline cursor-pointer"
                          title="Click to view formula and data lineage"
                        >
                          {fmtHours(c.turnaround_hours)}
                        </button>
                      ) : (
                        <button
                          onClick={() =>
                            setTraceabilityTarget({
                              call: c,
                              metricName: 'Turnaround',
                              traceability: c.durations_traceability['Turnaround'],
                            })
                          }
                          className="cursor-pointer"
                          title={c.turnaround_unavailable_reason || 'Metric unavailable'}
                        >
                          <StatusBadge label="Unavailable" tone="neutral" />
                        </button>
                      )}
                    </td>

                    {/* Anchorage Wait */}
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {c.anchorage_wait_hours !== null ? (
                        <button
                          onClick={() =>
                            setTraceabilityTarget({
                              call: c,
                              metricName: 'Anchorage Wait',
                              traceability: c.durations_traceability['Anchorage Wait'],
                            })
                          }
                          className="text-[var(--color-text-primary)] hover:text-[var(--color-accent)] hover:underline cursor-pointer"
                        >
                          {fmtHours(c.anchorage_wait_hours)}
                        </button>
                      ) : (
                        <span className="text-[10px] text-[var(--color-text-tertiary)]">⊘ UNAVAIL</span>
                      )}
                    </td>

                    {/* Berth Stay */}
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {c.berth_stay_hours !== null ? (
                        <button
                          onClick={() =>
                            setTraceabilityTarget({
                              call: c,
                              metricName: 'Berth Stay',
                              traceability: c.durations_traceability['Berth Stay'],
                            })
                          }
                          className="text-[var(--color-text-primary)] hover:text-[var(--color-accent)] hover:underline cursor-pointer"
                        >
                          {fmtHours(c.berth_stay_hours)}
                        </button>
                      ) : (
                        <span className="text-[10px] text-[var(--color-text-tertiary)]">—</span>
                      )}
                    </td>

                    {/* Inward Movement */}
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {c.inward_movement_hours !== null ? (
                        <button
                          onClick={() =>
                            setTraceabilityTarget({
                              call: c,
                              metricName: 'Inward Movement',
                              traceability: c.durations_traceability['Inward Movement'],
                            })
                          }
                          className="text-[var(--color-text-primary)] hover:text-[var(--color-accent)] hover:underline cursor-pointer"
                        >
                          {fmtHours(c.inward_movement_hours)}
                        </button>
                      ) : (
                        <span className="text-[10px] text-[var(--color-text-tertiary)]">⊘ UNAVAIL</span>
                      )}
                    </td>

                    {/* Delays Count & Hours */}
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {c.delays_count > 0 ? (
                        <span className="text-[var(--color-warning)] font-semibold" title={`${c.delays_count} recorded delays`}>
                          {fmtHours(c.total_delay_hours)} ({c.delays_count})
                        </span>
                      ) : (
                        <span className="text-[var(--color-text-tertiary)]">0h</span>
                      )}
                    </td>

                    {/* Action Button: Drill-down to Journey */}
                    <td className="px-3 py-2.5 text-center whitespace-nowrap">
                      <Link
                        href={`/vessel-journey?vcn=${c.vcn}`}
                        className="px-2.5 py-1 bg-[var(--color-accent)] text-white rounded-md text-[11px] font-medium hover:bg-[var(--color-accent-hover)] transition-colors cursor-pointer"
                      >
                        Journey →
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 4. Footer Pagination Controls */}
      <div className="bg-[var(--color-surface)] border-t border-[var(--color-border)] px-6 py-2.5 flex items-center justify-between gap-4 flex-wrap flex-shrink-0 text-xs text-[var(--color-text-secondary)]">
        <div>
          Showing{' '}
          <span className="font-semibold text-[var(--color-text-primary)]">
            {filteredCalls.length === 0 ? 0 : (page - 1) * pageSize + 1}
          </span>{' '}
          to{' '}
          <span className="font-semibold text-[var(--color-text-primary)]">
            {Math.min(page * pageSize, filteredCalls.length)}
          </span>{' '}
          of <span className="font-semibold text-[var(--color-text-primary)]">{filteredCalls.length}</span> vessel calls
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2.5 py-1 rounded-md border border-[var(--color-border-strong)] text-[var(--color-text-primary)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] disabled:opacity-40 cursor-pointer"
          >
            ← Previous
          </button>
          <span className="font-mono text-[var(--color-text-primary)]">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-2.5 py-1 rounded-md border border-[var(--color-border-strong)] text-[var(--color-text-primary)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] disabled:opacity-40 cursor-pointer"
          >
            Next →
          </button>
        </div>
      </div>

      {/* 5. Traceability Drawer (spec §2: formula + version + source records + filters + exclusions + DQ status) */}
      {traceabilityTarget && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/20 backdrop-blur-[1px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="drawer-title"
        >
          <div className="w-full max-w-md bg-[var(--color-surface)] h-full shadow-[0_0_24px_rgba(15,23,42,0.12)] flex flex-col border-l border-[var(--color-border)] animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-5 py-4 flex items-center justify-between flex-shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] font-semibold">
                  Metric Traceability &amp; Lineage
                </div>
                <h2 id="drawer-title" className="text-sm font-semibold mt-0.5 text-[var(--color-text-primary)]">
                  {traceabilityTarget.metricName} — {traceabilityTarget.call.vcn}
                </h2>
              </div>
              <button
                onClick={() => setTraceabilityTarget(null)}
                className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-lg font-bold p-1 cursor-pointer"
                aria-label="Close Traceability Drawer"
              >
                ✕
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
              {/* Value Banner */}
              <div className="p-3 bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-md">
                <div className="text-[var(--color-text-tertiary)] text-[10px] uppercase font-semibold">Calculated Value</div>
                <div className="text-xl font-semibold font-mono text-[var(--color-text-primary)] mt-0.5">
                  {traceabilityTarget.traceability.status === 'AVAILABLE' &&
                  traceabilityTarget.traceability.duration_hours !== null
                    ? `${traceabilityTarget.traceability.duration_hours.toFixed(2)} hours (${fmtHours(
                        traceabilityTarget.traceability.duration_hours
                      )})`
                    : 'UNAVAILABLE'}
                </div>
                {traceabilityTarget.traceability.unavailable_reason && (
                  <div className="mt-1 text-[var(--color-critical)] font-medium">
                    Reason: {traceabilityTarget.traceability.unavailable_reason}
                  </div>
                )}
              </div>

              {/* Formula & Version */}
              <div className="border border-[var(--color-border)] rounded-md p-3">
                <div className="font-semibold text-[var(--color-text-primary)] text-xs mb-1">Governed Formula</div>
                <div className="font-mono bg-[var(--color-surface-muted)] p-2 rounded text-[11px] text-[var(--color-text-secondary)]">
                  {traceabilityTarget.metricName === 'Turnaround'
                    ? 'ATD - ATA'
                    : traceabilityTarget.metricName === 'Anchorage Wait'
                    ? 'ANCHORAGE_ARRIVAL → PILOT_ON_BOARD_ARRIVAL'
                    : traceabilityTarget.metricName === 'Inward Movement'
                    ? 'PILOT_ON_BOARD_ARRIVAL → ALL_FAST_ARRIVAL'
                    : traceabilityTarget.metricName === 'Berth Stay'
                    ? 'ALL_FAST_ARRIVAL → LAST_LINE_UNTIED_SAILING'
                    : traceabilityTarget.metricName === 'Cargo Working'
                    ? 'CARGO_START → CARGO_END'
                    : traceabilityTarget.metricName === 'Outward Movement'
                    ? 'PILOT_ON_BOARD_SAILING → BREAKWATER_OUT'
                    : `${traceabilityTarget.metricName} (Governed Lead Time Catalogue)`}
                </div>
                <div className="flex justify-between text-[10px] text-[var(--color-text-tertiary)] mt-2">
                  <span>Formula Version: <strong>{traceabilityTarget.traceability.formula_version}</strong></span>
                  <span>Unit: <strong>hours (decimal)</strong></span>
                </div>
              </div>

              {/* Source Records */}
              <div className="border border-[var(--color-border)] rounded-md p-3">
                <div className="font-semibold text-[var(--color-text-primary)] text-xs mb-1">Underlying Source Records</div>
                {traceabilityTarget.traceability.source_records.length > 0 ? (
                  <ul className="space-y-1 font-mono text-[10px] text-[var(--color-text-secondary)]">
                    {traceabilityTarget.traceability.source_records.map((recId) => (
                      <li key={recId} className="bg-[var(--color-surface-muted)] p-1.5 rounded border border-[var(--color-border)] truncate">
                        UUID: {recId}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[var(--color-text-tertiary)] text-[11px]">No source records attached (Metric UNAVAILABLE)</p>
                )}
              </div>

              {/* Event Boundaries */}
              {(traceabilityTarget.traceability.start_time || traceabilityTarget.traceability.end_time) && (
                <div className="border border-[var(--color-border)] rounded-md p-3">
                  <div className="font-semibold text-[var(--color-text-primary)] text-xs mb-1">Timestamp Envelope Boundaries</div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <span className="text-[var(--color-text-tertiary)] block text-[10px]">Start Event:</span>
                      <span className="font-mono text-[var(--color-text-secondary)]">
                        {fmtTimestamp(traceabilityTarget.traceability.start_time)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[var(--color-text-tertiary)] block text-[10px]">End Event:</span>
                      <span className="font-mono text-[var(--color-text-secondary)]">
                        {fmtTimestamp(traceabilityTarget.traceability.end_time)}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Applied Filters & Exclusions */}
              <div className="border border-[var(--color-border)] rounded-md p-3">
                <div className="font-semibold text-[var(--color-text-primary)] text-xs mb-1">Applied Filters &amp; Exclusions</div>
                <div className="text-[11px] text-[var(--color-text-secondary)] space-y-1">
                  <div>
                    Port: <strong>{traceabilityTarget.call.port_id || 'ZADUR'}</strong> | Terminal:{' '}
                    <strong>{traceabilityTarget.call.terminal_id || 'DCT'}</strong>
                  </div>
                  <div>
                    Vessel Type: <strong>{traceabilityTarget.call.vessel_type || 'All'}</strong>
                  </div>
                  <div>
                    Exclusions: {traceabilityTarget.traceability.exclusions.length > 0 ? (
                      <span className="text-[var(--color-critical)] font-semibold">
                        {traceabilityTarget.traceability.exclusions.join(', ')}
                      </span>
                    ) : (
                      <span className="text-[var(--color-text-secondary)]">None</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Data Quality Status */}
              <div className="border border-[var(--color-border)] rounded-md p-3">
                <div className="font-semibold text-[var(--color-text-primary)] text-xs mb-1">Data Quality Validation State</div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={traceabilityTarget.call.quality_status} />
                  <span className="text-[var(--color-text-secondary)] text-[11px]">
                    Quality Score: {traceabilityTarget.call.quality_score}/100
                  </span>
                </div>
              </div>

              {/* Direct Drill-Through CTA */}
              <div className="pt-2">
                <Link
                  href={`/vessel-journey?vcn=${traceabilityTarget.call.vcn}`}
                  className="w-full py-2 bg-[var(--color-accent)] text-white rounded-md text-center block text-xs font-semibold hover:bg-[var(--color-accent-hover)] transition-colors"
                >
                  Inspect Full Journey Swimlane →
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function VesselCallsPage() {
  return (
    <React.Suspense fallback={<LoadingState label="Loading Vessel Calls…" />}>
      <VesselCallsContent />
    </React.Suspense>
  )
}
