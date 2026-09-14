'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'
import { PageHeader, StatusBadge, EmptyState, LoadingState, ErrorState, statusToTone } from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Types ────────────────────────────────────────────────────────────────────

interface VesselCallSummary {
  id: string
  vcn: string
  vessel_name: string
  ata?: string
  atd?: string
  tenant_id: string
  is_merged: boolean
}

interface StageRow {
  id: string
  stage_name: string
  sequence_index: number
  shift_occurrence_index: number
  availability: 'AVAILABLE' | 'UNAVAILABLE'
  is_missing: boolean
  is_inferred: boolean
  inference_reason?: string
  start_time?: string
  end_time?: string
  duration_hours?: number
  time_category: string
  status: string
  deviation_type?: string
  deviation_detail?: { description: string; duration_hours: number }
}

interface HandoverRow {
  from_stage_occurrence_id: string
  to_stage_occurrence_id: string
  from_actor?: string
  to_actor?: string
  status: string
  handover_time?: string
  wait_duration_hours?: number
}

interface JourneyData {
  vessel_call_id: string
  vcn: string
  vessel_name: string
  journey_instance_id: string
  status: string
  reconstruction_version: number
  rule_version?: string
  computed_at?: string
  coverage_summary?: {
    stages_total: number
    stages_available: number
    stages_missing: number
    stages_inferred: number
    shifting_occurrences: number
  }
  time_decomposition?: {
    ACTIVE_SERVICE: number
    PASSIVE_WAIT: number
    HOLD: number
    DELAY: number
    UNCLASSIFIED: number
    total_hours: number
    status: string
  }
  deviation_report?: Array<{ stage: string; type: string; detail: unknown }>
  stages: StageRow[]
  handovers: HandoverRow[]
}

interface ConflictRow {
  id: string
  event_definition_id: string
  candidate_event_occurrence_ids: string[]
  selected_event_occurrence_id?: string
  conflict_detected: boolean
  selection_method: string
  selection_reasoning?: {
    method?: string
    comparison?: Array<{
      event_occurrence_id: string
      source_system: string
      verification_status: string
      confidence: number
      utc_value?: string
      selected: boolean
    }>
    winning_reason?: string
  }
  decided_by?: string
  decided_at?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(h: number | null | undefined): string {
  if (h == null) return '—'
  const sign = h < 0 ? '-' : ''
  const abs = Math.abs(h)
  const hh = Math.floor(abs)
  const mm = Math.round((abs - hh) * 60)
  return `${sign}${hh}h ${mm}m`
}

function fmtTs(ts: string | undefined | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', hour12: false })
  } catch {
    return ts
  }
}

/** Maps internal time-category vocabulary to a StatusBadge tone. */
function categoryTone(cat: string): 'good' | 'warning' | 'critical' | 'inferred' | 'neutral' {
  switch (cat) {
    case 'ACTIVE_SERVICE': return 'good'
    case 'PASSIVE_WAIT': return 'neutral'
    case 'HOLD': return 'warning'
    case 'DELAY': return 'critical'
    default: return 'neutral'
  }
}

function CategoryBadge({ cat }: { cat: string }) {
  return <StatusBadge label={cat.replace('_', ' ')} tone={categoryTone(cat)} showGlyph={false} />
}

function availabilityBadge(row: StageRow) {
  if (row.availability !== 'AVAILABLE') {
    return <StatusBadge label="Unavailable" tone="neutral" />
  }
  if (row.deviation_type === 'SEQUENCE_VIOLATION') {
    return <StatusBadge label="Sequence Violation" tone="critical" />
  }
  if (row.is_inferred) {
    return <StatusBadge label="Inferred" tone="inferred" />
  }
  return <StatusBadge label="Available" tone="good" />
}

// ── Components ───────────────────────────────────────────────────────────────

function DecompositionBar({ d }: { d: NonNullable<JourneyData['time_decomposition']> }) {
  const total = d.total_hours || 1
  const cats = [
    { key: 'ACTIVE_SERVICE', label: 'Active', color: 'bg-[var(--color-good)]' },
    { key: 'PASSIVE_WAIT', label: 'Wait', color: 'bg-[var(--color-neutral)]' },
    { key: 'HOLD', label: 'Hold', color: 'bg-[var(--color-warning)]' },
    { key: 'DELAY', label: 'Delay', color: 'bg-[var(--color-critical)]' },
    { key: 'UNCLASSIFIED', label: 'Unclassified', color: 'bg-[var(--color-border-strong)]' },
  ] as const

  return (
    <div className="mt-2">
      <div className="flex h-3 rounded-full overflow-hidden bg-[var(--color-surface-muted)]">
        {cats.map(({ key, label, color }) => {
          const val = d[key] as number
          if (!val || val <= 0) return null
          const pct = (val / total) * 100
          return (
            <div
              key={key}
              className={color}
              style={{ width: `${pct}%` }}
              title={`${label}: ${fmt(val)}`}
            />
          )
        })}
      </div>
      <div className="flex gap-4 mt-2 flex-wrap">
        {cats.map(({ key, label, color }) => {
          const val = d[key] as number
          return (
            <span key={key} className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)]">
              <span className={`inline-block w-2 h-2 rounded-sm ${color}`} />
              {label}: {fmt(val)}
            </span>
          )
        })}
        <span className="text-xs font-semibold text-[var(--color-text-primary)] ml-auto">
          Total: {fmt(d.total_hours)}
        </span>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

import { useRouter, useSearchParams } from 'next/navigation'

interface RawEventRow {
  id: string
  event_name: string
  category: string
  original_string: string
  utc_value: string
  timezone: string
  source_system: string
  source_record_id: string
  verification_status: string
  confidence: number
  is_quarantined: boolean
  capture_method: string
}

const TABS = [
  { id: 'swimlane', label: 'Operational Swimlane' },
  { id: 'timeline', label: 'Stage Details' },
  { id: 'events', label: 'Raw Envelopes' },
  { id: 'decomposition', label: 'Time Decomposition' },
  { id: 'conflicts', label: 'Conflicts' },
  { id: 'history', label: 'History' },
] as const

function VesselJourneyContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { token } = useAuth()

  const [vesselCalls, setVesselCalls] = useState<VesselCallSummary[]>([])
  const [search, setSearch] = useState('')
  const [selectedVcId, setSelectedVcId] = useState<string | null>(null)
  const [journey, setJourney] = useState<JourneyData | null>(null)
  const [conflicts, setConflicts] = useState<ConflictRow[]>([])
  const [rawEvents, setRawEvents] = useState<RawEventRow[]>([])
  const [loadingList, setLoadingList] = useState(true)
  const [loadingJourney, setLoadingJourney] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'timeline' | 'swimlane' | 'decomposition' | 'events' | 'conflicts' | 'history'>('swimlane')
  const [reconstructing, setReconstructing] = useState(false)
  const [reconstructMsg, setReconstructMsg] = useState<string | null>(null)
  const [historyRows, setHistoryRows] = useState<Array<{ run_version: number; rule_version?: string; triggered_by: string; created_at?: string; snapshot: unknown }>>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const headers = { Authorization: `Bearer ${token || 'dev-token'}` }

  // Load vessel call list
  useEffect(() => {
    setLoadingList(true)
    fetch(`${API}/api/v1/operations/vessel-calls?limit=200`, { headers })
      .then((r) => r.json())
      .then((d) => {
        const items: VesselCallSummary[] = Array.isArray(d) ? d : (d.items ?? [])
        const cleanCalls = items.filter((v) => !v.is_merged)
        setVesselCalls(cleanCalls)

        // Check if query params specify a VCN or ID
        const targetVcn = searchParams.get('vcn')
        const targetId = searchParams.get('id')
        if (targetVcn) {
          const match = cleanCalls.find((c) => c.vcn.toLowerCase() === targetVcn.toLowerCase())
          if (match) {
            setSelectedVcId(match.id)
            loadJourney(match.id)
          }
        } else if (targetId) {
          const match = cleanCalls.find((c) => c.id === targetId)
          if (match) {
            setSelectedVcId(match.id)
            loadJourney(match.id)
          }
        }
      })
      .catch(() => setError('Failed to load vessel calls'))
      .finally(() => setLoadingList(false))
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadJourney = useCallback(
    (vcId: string) => {
      setLoadingJourney(true)
      setJourney(null)
      setConflicts([])
      setRawEvents([])
      setError(null)

      Promise.all([
        fetch(`${API}/api/v1/journey/${vcId}`, { headers }).then((r) =>
          r.ok ? r.json() : Promise.reject(r.statusText)
        ),
        fetch(`${API}/api/v1/journey/${vcId}/conflicts`, { headers }).then((r) =>
          r.ok ? r.json() : []
        ),
        fetch(`${API}/api/v1/journey/${vcId}/events`, { headers }).then((r) =>
          r.ok ? r.json() : []
        ),
      ])
        .then(([j, c, evs]: [JourneyData, ConflictRow[], RawEventRow[]]) => {
          setJourney(j)
          setConflicts(c)
          setRawEvents(evs)
        })
        .catch(() => setError('No reconstructed journey for this vessel call. Use Reconstruct to build it.'))
        .finally(() => setLoadingJourney(false))
    },
    [token] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const handleSelect = (vcId: string) => {
    setSelectedVcId(vcId)
    const match = vesselCalls.find((v) => v.id === vcId)
    if (match) {
      router.replace(`/vessel-journey?vcn=${match.vcn}`)
    }
    loadJourney(vcId)
  }

  const handleReconstruct = () => {
    if (!selectedVcId) return
    setReconstructing(true)
    setReconstructMsg(null)
    fetch(`${API}/api/v1/journey/reconstruct?vessel_call_id=${selectedVcId}`, {
      method: 'POST',
      headers,
    })
      .then((r) => r.json())
      .then((d) => {
        setReconstructMsg(`Reconstructed (version ${d.journey_instance_id?.slice(0, 8) ?? '?'})`)
        loadJourney(selectedVcId)
      })
      .catch(() => setReconstructMsg('Reconstruction failed'))
      .finally(() => setReconstructing(false))
  }

  const handleLoadHistory = () => {
    if (!selectedVcId) return
    setLoadingHistory(true)
    fetch(`${API}/api/v1/journey/${selectedVcId}/history`, { headers })
      .then((r) => r.json())
      .then(setHistoryRows)
      .finally(() => setLoadingHistory(false))
  }

  const filtered = vesselCalls.filter(
    (v) =>
      v.vcn.toLowerCase().includes(search.toLowerCase()) ||
      v.vessel_name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="h-full flex gap-0 overflow-hidden bg-[var(--color-bg)]">
      {/* ── LEFT: Vessel Call List ─────────────────────────────────────── */}
      <aside className="w-64 flex-shrink-0 bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col overflow-hidden">
        <div className="p-3 border-b border-[var(--color-border)]">
          <h2 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide mb-2">
            Vessel Calls
          </h2>
          <input
            type="text"
            placeholder="Search VCN or vessel name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-xs bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md px-2.5 py-1.5 text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingList ? (
            <LoadingState label="Loading vessel calls…" />
          ) : filtered.length === 0 ? (
            <EmptyState title="No vessel calls found" />
          ) : (
            filtered.map((vc) => (
              <button
                key={vc.id}
                onClick={() => handleSelect(vc.id)}
                className={`w-full text-left px-3 py-2.5 border-b border-[var(--color-border)] text-xs transition-colors cursor-pointer ${
                  selectedVcId === vc.id
                    ? 'bg-[var(--color-accent-soft)] border-l-2 border-l-[var(--color-accent)]'
                    : 'hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                <div className="font-semibold text-[var(--color-text-primary)] truncate">{vc.vcn}</div>
                <div className="text-[var(--color-text-secondary)] truncate">{vc.vessel_name}</div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* ── RIGHT: Journey Detail ─────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!selectedVcId ? (
          <EmptyState
            className="flex-1"
            title="Select a vessel call"
            description="Choose a vessel call from the list to view its journey reconstruction."
          />
        ) : loadingJourney ? (
          <LoadingState className="flex-1" label="Loading journey…" />
        ) : error && !journey ? (
          <ErrorState
            className="flex-1"
            title="No reconstructed journey"
            description={error}
            onRetry={handleReconstruct}
          />
        ) : journey ? (
          <>
            {/* Header */}
            <PageHeader
              title={`${journey.vcn} — ${journey.vessel_name}`}
              meta={
                <div className="flex flex-col gap-1.5">
                  <div className="flex gap-4 flex-wrap items-center">
                    <span>
                      Status: <StatusBadge status={journey.status} showGlyph={false} className="ml-1" />
                    </span>
                    <span>
                      Version: <span className="font-semibold text-[var(--color-text-primary)]">{journey.reconstruction_version}</span>
                    </span>
                    <span>
                      Rule: <span className="font-semibold text-[var(--color-text-primary)]">{journey.rule_version ?? '—'}</span>
                    </span>
                    <span>
                      Computed: <span className="font-semibold text-[var(--color-text-primary)]">{fmtTs(journey.computed_at)}</span>
                    </span>
                  </div>
                  {journey.coverage_summary && (
                    <div className="flex gap-4 flex-wrap items-center">
                      <span>
                        Stages: {journey.coverage_summary.stages_available} available /{' '}
                        {journey.coverage_summary.stages_missing} missing /{' '}
                        {journey.coverage_summary.stages_inferred} inferred /{' '}
                        {journey.coverage_summary.stages_total} total
                      </span>
                      {journey.coverage_summary.shifting_occurrences > 0 && (
                        <StatusBadge
                          label={`${journey.coverage_summary.shifting_occurrences} shift(s)`}
                          tone="warning"
                        />
                      )}
                      {conflicts.filter((c) => c.conflict_detected).length > 0 && (
                        <StatusBadge
                          label={`${conflicts.filter((c) => c.conflict_detected).length} observation conflict(s)`}
                          tone="critical"
                        />
                      )}
                    </div>
                  )}
                </div>
              }
              actions={
                <div className="flex items-center gap-3">
                  {reconstructMsg && (
                    <span className="text-xs text-[var(--color-good)]">{reconstructMsg}</span>
                  )}
                  <button
                    onClick={handleReconstruct}
                    disabled={reconstructing}
                    className="px-3 py-1.5 bg-[var(--color-accent)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-accent-hover)] disabled:opacity-50 cursor-pointer"
                  >
                    {reconstructing ? 'Reconstructing…' : '↺ Reconstruct'}
                  </button>
                </div>
              }
            />

            {/* Intentional DQ Callout Banners */}
            {journey.vcn === 'SYNVCN2600018' && (
              <div className="bg-[var(--color-warning-bg)] border-b border-[var(--color-warning-border)] px-6 py-2.5 text-xs text-[var(--color-text-primary)] flex items-center gap-2 flex-shrink-0">
                <StatusBadge label="DQ-003 Case" tone="warning" />
                <span>Missing mandatory ATA in staging record. Dependent durations (Turnaround, Inward Movement) are formally preserved as <strong>UNAVAILABLE</strong> with explicit reason. No fake zeroes are fabricated.</span>
              </div>
            )}
            {journey.vcn === 'SYNVCN2600070' && (
              <div className="bg-[var(--color-accent-soft)] border-b border-[var(--color-accent-soft-border)] px-6 py-2.5 text-xs text-[var(--color-text-primary)] flex items-center gap-2 flex-shrink-0">
                <StatusBadge label="DQ-010 Case" tone="neutral" />
                <span>Two conflicting ATA timestamps received (AIS 15:22 vs Manual Log 20:22). Both observations are preserved in canonical storage; inspect the <strong>Conflicts</strong> tab for the winning selection.</span>
              </div>
            )}
            {journey.vcn === 'SYNVCN2600045' && (
              <div className="bg-[var(--color-critical-bg)] border-b border-[var(--color-critical-border)] px-6 py-2.5 text-xs text-[var(--color-text-primary)] flex items-center gap-2 flex-shrink-0">
                <StatusBadge label="DQ-006 Case" tone="critical" />
                <span>Chronology sequence violation detected (Pilot On Board before scheduled). Quarantined by Data Quality Engine without dropping the raw observation.</span>
              </div>
            )}

            {/* Tabs */}
            <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 flex gap-1 flex-shrink-0 overflow-x-auto">
              {TABS.map((t) => {
                const count =
                  t.id === 'events'
                    ? rawEvents.length
                    : t.id === 'conflicts'
                    ? conflicts.filter((c) => c.conflict_detected).length
                    : null
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      setTab(t.id)
                      if (t.id === 'history') handleLoadHistory()
                    }}
                    className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors cursor-pointer whitespace-nowrap ${
                      tab === t.id
                        ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                        : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                    }`}
                  >
                    {t.label}
                    {count !== null && <span className="ml-1 text-[var(--color-text-tertiary)]">({count})</span>}
                  </button>
                )
              })}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* ── Operational Swimlane ── */}
              {tab === 'swimlane' && (
                <div className="space-y-5">
                  {/* Path comparison banner */}
                  <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-4 text-xs">
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                      <span className="font-semibold text-sm text-[var(--color-text-primary)]">
                        Operational Flow: Standard Path vs Actual Reconstructed Path
                      </span>
                      <StatusBadge
                        label={
                          journey.coverage_summary?.shifting_occurrences
                            ? 'Actual: Non-Standard Shifting Call'
                            : 'Actual: Standard Port Call'
                        }
                        tone={journey.coverage_summary?.shifting_occurrences ? 'warning' : 'good'}
                      />
                    </div>
                    <div className="flex items-center gap-2 flex-wrap text-[var(--color-text-secondary)] bg-[var(--color-surface-muted)] p-3 rounded-md border border-[var(--color-border)]">
                      <span className="px-2 py-0.5 bg-[var(--color-surface)] border border-[var(--color-border-strong)] rounded text-[var(--color-text-primary)] font-semibold">Standard:</span>
                      <span>Arrival</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Anchorage Wait</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Inward Pilotage</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Berthing</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Cargo Working</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Unberthing</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Outward Pilotage</span>
                      <span className="text-[var(--color-text-tertiary)]">→</span>
                      <span>Departure</span>
                    </div>
                  </div>

                  {/* Horizontal visual timeline of stage cards */}
                  <div className="relative">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      {journey.stages.map((s, idx) => {
                        const isAvail = s.availability === 'AVAILABLE'
                        const isViolation = s.deviation_type === 'SEQUENCE_VIOLATION'
                        const isShift = s.shift_occurrence_index > 0

                        return (
                          <div
                            key={s.id}
                            className={`relative rounded-lg border p-4 flex flex-col justify-between bg-[var(--color-surface)] text-xs shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${
                              isViolation
                                ? 'border-[var(--color-critical-border)]'
                                : !isAvail
                                ? 'border-[var(--color-border)] opacity-70'
                                : isShift
                                ? 'border-[var(--color-warning-border)]'
                                : 'border-[var(--color-border)]'
                            }`}
                          >
                            {/* Connector to next stage on wide layouts */}
                            {idx < journey.stages.length - 1 && (
                              <div
                                className="hidden lg:block absolute top-1/2 -right-4 w-4 h-0.5 bg-[var(--color-accent-soft-border)]"
                                aria-hidden="true"
                              />
                            )}
                            <div>
                              {/* Card top */}
                              <div className="flex items-center justify-between gap-1 mb-2">
                                <span className="text-[10px] font-semibold text-[var(--color-text-tertiary)] tabular-nums">
                                  STAGE #{idx + 1}
                                </span>
                                <CategoryBadge cat={s.time_category} />
                              </div>

                              {/* Stage Name */}
                              <div className="font-semibold text-[var(--color-text-primary)] text-sm truncate" title={s.stage_name}>
                                {s.stage_name}
                                {isShift && (
                                  <span className="ml-1 text-[var(--color-warning)] font-normal">
                                    #{s.shift_occurrence_index}
                                  </span>
                                )}
                              </div>

                              {/* Duration Ribbon Bar */}
                              <div className="mt-3 mb-2">
                                <div className="h-1.5 rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
                                  <div
                                    className={`h-full rounded-full ${
                                      isViolation
                                        ? 'bg-[var(--color-critical)]'
                                        : s.time_category === 'ACTIVE_SERVICE'
                                        ? 'bg-[var(--color-good)]'
                                        : s.time_category === 'PASSIVE_WAIT'
                                        ? 'bg-[var(--color-neutral)]'
                                        : s.time_category === 'HOLD'
                                        ? 'bg-[var(--color-warning)]'
                                        : 'bg-[var(--color-border-strong)]'
                                    }`}
                                    style={{ width: isAvail ? '100%' : '0%' }}
                                  />
                                </div>
                              </div>
                            </div>

                            {/* Duration and timestamps */}
                            <div className="mt-2 pt-3 border-t border-[var(--color-border)] space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-[var(--color-text-tertiary)]">Duration</span>
                                <span className="font-semibold text-[var(--color-text-primary)] tabular-nums">
                                  {isAvail ? fmt(s.duration_hours) : 'UNAVAILABLE'}
                                </span>
                              </div>

                              <div className="text-[10px] text-[var(--color-text-tertiary)] truncate">
                                Start: {fmtTs(s.start_time)}
                              </div>
                              <div className="text-[10px] text-[var(--color-text-tertiary)] truncate">
                                End: {fmtTs(s.end_time)}
                              </div>

                              {isViolation && (
                                <div className="pt-1">
                                  <StatusBadge label={s.deviation_detail?.description || 'Sequence violation'} tone="critical" />
                                </div>
                              )}
                              {s.is_inferred && (
                                <div className="pt-1">
                                  <StatusBadge label="Inferred observation" tone="inferred" />
                                </div>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* ── Raw Envelopes Tab ── */}
              {tab === 'events' && (
                <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] overflow-hidden">
                  <div className="p-4 bg-[var(--color-surface-muted)] border-b border-[var(--color-border)] flex items-center justify-between text-xs flex-wrap gap-2">
                    <span className="font-semibold text-sm text-[var(--color-text-primary)]">
                      Canonical Timestamp Envelopes &amp; Audit Trail
                    </span>
                    <span className="text-[var(--color-text-secondary)]">
                      {rawEvents.length} preserved event occurrences
                    </span>
                  </div>
                  {rawEvents.length === 0 ? (
                    <EmptyState title="No raw event occurrences" description="No canonical envelopes have been captured for this vessel call." />
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] font-semibold border-b border-[var(--color-border)]">
                          <tr>
                            <th className="px-4 py-2.5">Event Name</th>
                            <th className="px-4 py-2.5">Category</th>
                            <th className="px-4 py-2.5">Original String</th>
                            <th className="px-4 py-2.5">UTC Value</th>
                            <th className="px-4 py-2.5">Source</th>
                            <th className="px-4 py-2.5">Confidence</th>
                            <th className="px-4 py-2.5">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--color-border)]">
                          {rawEvents.map((ev) => (
                            <tr key={ev.id} className="hover:bg-[var(--color-surface-muted)]">
                              <td className="px-4 py-3 font-semibold text-[var(--color-text-primary)]">
                                {ev.event_name}
                              </td>
                              <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                                {ev.category}
                              </td>
                              <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                                {ev.original_string || '—'}
                              </td>
                              <td className="px-4 py-3 text-[var(--color-text-primary)]">
                                {fmtTs(ev.utc_value)}
                              </td>
                              <td className="px-4 py-3">
                                <StatusBadge label={ev.source_system} tone="neutral" showGlyph={false} />
                              </td>
                              <td className="px-4 py-3 text-[var(--color-text-secondary)] tabular-nums">
                                {ev.confidence !== null ? `${(ev.confidence * 100).toFixed(0)}%` : '—'}
                              </td>
                              <td className="px-4 py-3">
                                <StatusBadge
                                  label={ev.verification_status || 'Unverified'}
                                  tone={statusToTone(ev.verification_status)}
                                  showGlyph={false}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* ── Stage Details (formerly Timeline) ── */}
              {tab === 'timeline' && (
                <div className="space-y-2">
                  {journey.stages.map((s, i) => (
                    <div
                      key={s.id}
                      className={`rounded-lg border px-4 py-3 text-xs bg-[var(--color-surface)] ${
                        s.availability !== 'AVAILABLE'
                          ? 'border-[var(--color-border)] opacity-60'
                          : s.deviation_type === 'SEQUENCE_VIOLATION'
                          ? 'border-[var(--color-critical-border)] bg-[var(--color-critical-bg)]'
                          : 'border-[var(--color-border)]'
                      }`}
                    >
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-[10px] text-[var(--color-text-tertiary)] w-5 text-right tabular-nums">{i + 1}</span>
                        <span className="font-semibold text-[var(--color-text-primary)] flex-1 min-w-0 truncate text-sm">
                          {s.stage_name}
                          {s.shift_occurrence_index > 0 && (
                            <span className="ml-1 text-[var(--color-warning)] font-normal">
                              #{s.shift_occurrence_index}
                            </span>
                          )}
                        </span>
                        {availabilityBadge(s)}
                        <CategoryBadge cat={s.time_category} />
                      </div>
                      {s.availability === 'AVAILABLE' && (
                        <div className="flex gap-4 mt-2 ml-8 flex-wrap text-[var(--color-text-secondary)]">
                          <span>Start: {fmtTs(s.start_time)}</span>
                          <span>End: {fmtTs(s.end_time)}</span>
                          <span className="font-semibold text-[var(--color-text-primary)]">Duration: {fmt(s.duration_hours)}</span>
                          {s.deviation_type === 'SEQUENCE_VIOLATION' && (
                            <StatusBadge label={s.deviation_detail?.description || 'Sequence violation'} tone="critical" />
                          )}
                        </div>
                      )}
                      {s.availability !== 'AVAILABLE' && s.inference_reason && (
                        <div className="ml-8 mt-1 text-[var(--color-text-tertiary)] italic">
                          {s.inference_reason}
                        </div>
                      )}
                      {s.is_inferred && s.inference_reason && (
                        <div className="ml-8 mt-1 text-[var(--color-inferred)] italic">
                          Inferred: {s.inference_reason}
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Handovers */}
                  {journey.handovers.filter((h) => h.status === 'AVAILABLE').length > 0 && (
                    <div className="mt-6 pt-5 border-t border-[var(--color-border)]">
                      <h3 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide mb-3">
                        Stakeholder Handovers
                      </h3>
                      <div className="space-y-2">
                        {journey.handovers
                          .filter((h) => h.status === 'AVAILABLE')
                          .map((h, i) => (
                            <div
                              key={i}
                              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-xs text-[var(--color-text-secondary)] flex gap-4 flex-wrap"
                            >
                              <span>
                                <span className="font-semibold text-[var(--color-text-primary)]">{h.from_actor ?? '—'}</span>
                                {' → '}
                                <span className="font-semibold text-[var(--color-text-primary)]">{h.to_actor ?? '—'}</span>
                              </span>
                              <span>At: {fmtTs(h.handover_time)}</span>
                              {h.wait_duration_hours != null && (
                                <span>
                                  Wait: {fmt(h.wait_duration_hours)}
                                </span>
                              )}
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Deviation report */}
                  {journey.deviation_report && journey.deviation_report.length > 0 && (
                    <div className="mt-6 pt-5 border-t border-[var(--color-border)]">
                      <h3 className="text-xs font-semibold text-[var(--color-critical)] uppercase tracking-wide mb-3">
                        Operational Deviations
                      </h3>
                      <div className="space-y-2">
                        {journey.deviation_report.map((d, i) => (
                          <div
                            key={i}
                            className="rounded-lg border border-[var(--color-critical-border)] bg-[var(--color-critical-bg)] px-4 py-2.5 text-xs text-[var(--color-text-primary)]"
                          >
                            <span className="font-semibold">{d.stage}</span> — {d.type}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Decomposition ── */}
              {tab === 'decomposition' && (
                <div className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] p-5">
                  {journey.time_decomposition && journey.time_decomposition.status === 'AVAILABLE' ? (
                    <>
                      <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
                        Active / Wait / Hold / Delay / Unclassified Decomposition
                      </h3>
                      <DecompositionBar d={journey.time_decomposition} />
                      <table className="mt-6 w-full text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-[var(--color-border)]">
                            <th className="text-left py-2 text-[var(--color-text-secondary)] font-semibold">Category</th>
                            <th className="text-right py-2 text-[var(--color-text-secondary)] font-semibold">Hours</th>
                            <th className="text-right py-2 text-[var(--color-text-secondary)] font-semibold">%</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(['ACTIVE_SERVICE', 'PASSIVE_WAIT', 'HOLD', 'DELAY', 'UNCLASSIFIED'] as const).map(
                            (cat) => {
                              const val = journey.time_decomposition![cat]
                              const pct =
                                journey.time_decomposition!.total_hours
                                  ? ((val / journey.time_decomposition!.total_hours) * 100).toFixed(1)
                                  : '—'
                              return (
                                <tr key={cat} className="border-b border-[var(--color-border)]">
                                  <td className="py-2.5">
                                    <CategoryBadge cat={cat} />
                                  </td>
                                  <td className="text-right text-[var(--color-text-primary)] tabular-nums">{fmt(val)}</td>
                                  <td className="text-right text-[var(--color-text-secondary)] tabular-nums">{pct}%</td>
                                </tr>
                              )
                            }
                          )}
                          <tr className="font-semibold text-[var(--color-text-primary)]">
                            <td className="py-3">Total</td>
                            <td className="text-right tabular-nums">
                              {fmt(journey.time_decomposition.total_hours)}
                            </td>
                            <td className="text-right">100%</td>
                          </tr>
                        </tbody>
                      </table>
                      <p className="mt-4 text-xs text-[var(--color-text-tertiary)] italic">
                        Components are non-overlapping. Shifting time is carved out of the containing
                        stage&apos;s bucket and recorded under DELAY.
                      </p>
                    </>
                  ) : (
                    <EmptyState
                      title="Time decomposition unavailable"
                      description="Insufficient stage data to compute the active/wait/hold/delay breakdown."
                    />
                  )}
                </div>
              )}

              {/* ── Conflicts ── */}
              {tab === 'conflicts' && (
                <div className="space-y-3">
                  {conflicts.filter((c) => c.conflict_detected).length === 0 ? (
                    <EmptyState title="No observation conflicts" description="No observation conflicts detected for this vessel call." />
                  ) : (
                    conflicts
                      .filter((c) => c.conflict_detected)
                      .map((c) => (
                        <div
                          key={c.id}
                          className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-warning-border)] px-5 py-4 text-xs"
                        >
                          <div className="flex items-center gap-2 mb-3 flex-wrap">
                            <StatusBadge label="Conflict" tone="warning" />
                            <span className="font-semibold text-[var(--color-text-primary)]">
                              Event Definition: {c.event_definition_id.slice(0, 8)}…
                            </span>
                            <span className="text-[var(--color-text-tertiary)]">
                              Method: {c.selection_method}
                            </span>
                          </div>
                          {c.selection_reasoning?.comparison && (
                            <div className="space-y-1.5 mt-2">
                              <p className="text-[10px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
                                Competing observations — all retained, none deleted:
                              </p>
                              {c.selection_reasoning.comparison.map((obs) => (
                                <div
                                  key={obs.event_occurrence_id}
                                  className={`rounded-md px-3 py-2 flex gap-4 flex-wrap items-center ${
                                    obs.selected
                                      ? 'bg-[var(--color-good-bg)] border border-[var(--color-good-border)]'
                                      : 'bg-[var(--color-surface-muted)] border border-[var(--color-border)]'
                                  }`}
                                >
                                  <span className="text-[var(--color-text-tertiary)]">
                                    {obs.event_occurrence_id.slice(0, 8)}…
                                  </span>
                                  <span>Source: <strong className="text-[var(--color-text-primary)]">{obs.source_system}</strong></span>
                                  <span>Verification: <strong className="text-[var(--color-text-primary)]">{obs.verification_status}</strong></span>
                                  <span>Confidence: {obs.confidence}</span>
                                  <span>UTC: {fmtTs(obs.utc_value)}</span>
                                  {obs.selected && <StatusBadge label="Canonical" tone="good" />}
                                </div>
                              ))}
                            </div>
                          )}
                          {c.selection_reasoning?.winning_reason && (
                            <p className="mt-3 text-[var(--color-text-secondary)] italic">
                              Selection rationale: {c.selection_reasoning.winning_reason}
                            </p>
                          )}
                          <p className="mt-2 text-[var(--color-text-tertiary)]">
                            Decided by: {c.decided_by ?? '—'} at {fmtTs(c.decided_at)}
                          </p>
                        </div>
                      ))
                  )}
                </div>
              )}

              {/* ── History ── */}
              {tab === 'history' && (
                <div>
                  {loadingHistory ? (
                    <LoadingState label="Loading history…" />
                  ) : historyRows.length === 0 ? (
                    <EmptyState title="No reconstruction history" description="No reconstruction runs have been recorded yet." />
                  ) : (
                    <div className="space-y-2">
                      {historyRows.map((h) => (
                        <div
                          key={h.run_version}
                          className="bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)] px-5 py-3 text-xs"
                        >
                          <div className="flex items-center gap-4 flex-wrap">
                            <span className="font-semibold text-[var(--color-text-primary)]">v{h.run_version}</span>
                            <span className="text-[var(--color-text-secondary)]">Rule: {h.rule_version ?? '—'}</span>
                            <span className="text-[var(--color-text-secondary)]">Trigger: {h.triggered_by}</span>
                            <span className="text-[var(--color-text-tertiary)] ml-auto">{fmtTs(h.created_at)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        ) : null}
      </main>
    </div>
  )
}

export default function VesselJourneyPage() {
  return (
    <React.Suspense fallback={<LoadingState className="p-8" label="Loading Vessel Journey..." />}>
      <VesselJourneyContent />
    </React.Suspense>
  )
}
