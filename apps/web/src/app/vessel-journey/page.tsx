'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'

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

function categoryColor(cat: string): string {
  switch (cat) {
    case 'ACTIVE_SERVICE': return 'bg-emerald-100 text-emerald-800'
    case 'PASSIVE_WAIT': return 'bg-sky-100 text-sky-800'
    case 'HOLD': return 'bg-amber-100 text-amber-800'
    case 'DELAY': return 'bg-red-100 text-red-800'
    default: return 'bg-slate-100 text-slate-700'
  }
}

function availabilityBadge(row: StageRow) {
  if (row.availability !== 'AVAILABLE') {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-200 text-slate-600">
        UNAVAILABLE
      </span>
    )
  }
  if (row.deviation_type === 'SEQUENCE_VIOLATION') {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-100 text-red-700">
        SEQUENCE VIOLATION
      </span>
    )
  }
  if (row.is_inferred) {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700">
        INFERRED
      </span>
    )
  }
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-700">
      AVAILABLE
    </span>
  )
}

// ── Components ───────────────────────────────────────────────────────────────

function DecompositionBar({ d }: { d: NonNullable<JourneyData['time_decomposition']> }) {
  const total = d.total_hours || 1
  const cats = [
    { key: 'ACTIVE_SERVICE', label: 'Active', color: 'bg-emerald-500' },
    { key: 'PASSIVE_WAIT', label: 'Wait', color: 'bg-sky-400' },
    { key: 'HOLD', label: 'Hold', color: 'bg-amber-400' },
    { key: 'DELAY', label: 'Delay', color: 'bg-red-400' },
    { key: 'UNCLASSIFIED', label: 'Unclassified', color: 'bg-slate-300' },
  ] as const

  return (
    <div className="mt-2">
      <div className="flex h-5 rounded overflow-hidden">
        {cats.map(({ key, label, color }) => {
          const val = d[key] as number
          if (!val || val <= 0) return null
          const pct = (val / total) * 100
          return (
            <div
              key={key}
              className={`${color} flex items-center justify-center text-[9px] text-white font-bold`}
              style={{ width: `${pct}%` }}
              title={`${label}: ${fmt(val)}`}
            />
          )
        })}
      </div>
      <div className="flex gap-3 mt-1 flex-wrap">
        {cats.map(({ key, label, color }) => {
          const val = d[key] as number
          return (
            <span key={key} className="flex items-center gap-1 text-[10px] text-slate-600">
              <span className={`inline-block w-2 h-2 rounded-sm ${color}`} />
              {label}: {fmt(val)}
            </span>
          )
        })}
        <span className="text-[10px] font-semibold text-slate-700 ml-auto">
          Total: {fmt(d.total_hours)}
        </span>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function VesselJourneyPage() {
  const { token } = useAuth()

  const [vesselCalls, setVesselCalls] = useState<VesselCallSummary[]>([])
  const [search, setSearch] = useState('')
  const [selectedVcId, setSelectedVcId] = useState<string | null>(null)
  const [journey, setJourney] = useState<JourneyData | null>(null)
  const [conflicts, setConflicts] = useState<ConflictRow[]>([])
  const [loadingList, setLoadingList] = useState(true)
  const [loadingJourney, setLoadingJourney] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'timeline' | 'decomposition' | 'conflicts' | 'history'>('timeline')
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
        setVesselCalls(items.filter((v) => !v.is_merged))
      })
      .catch(() => setError('Failed to load vessel calls'))
      .finally(() => setLoadingList(false))
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadJourney = useCallback(
    (vcId: string) => {
      setLoadingJourney(true)
      setJourney(null)
      setConflicts([])
      setError(null)
      setTab('timeline')

      Promise.all([
        fetch(`${API}/api/v1/journey/${vcId}`, { headers }).then((r) =>
          r.ok ? r.json() : Promise.reject(r.statusText)
        ),
        fetch(`${API}/api/v1/journey/${vcId}/conflicts`, { headers }).then((r) =>
          r.ok ? r.json() : []
        ),
      ])
        .then(([j, c]: [JourneyData, ConflictRow[]]) => {
          setJourney(j)
          setConflicts(c)
        })
        .catch(() => setError('No reconstructed journey for this vessel call. Use Reconstruct to build it.'))
        .finally(() => setLoadingJourney(false))
    },
    [token] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const handleSelect = (vcId: string) => {
    setSelectedVcId(vcId)
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

  const selectedVc = vesselCalls.find((v) => v.id === selectedVcId)

  return (
    <div className="h-full flex gap-0 overflow-hidden">
      {/* ── LEFT: Vessel Call List ─────────────────────────────────────── */}
      <aside className="w-64 flex-shrink-0 bg-white border-r border-slate-200 flex flex-col overflow-hidden">
        <div className="p-3 border-b border-slate-200">
          <h2 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
            Vessel Calls
          </h2>
          <input
            type="text"
            placeholder="Search VCN or vessel name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-xs border border-slate-300 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingList ? (
            <p className="p-3 text-xs text-slate-400">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="p-3 text-xs text-slate-400">No vessel calls found.</p>
          ) : (
            filtered.map((vc) => (
              <button
                key={vc.id}
                onClick={() => handleSelect(vc.id)}
                className={`w-full text-left px-3 py-2.5 border-b border-slate-100 text-xs transition-colors ${
                  selectedVcId === vc.id
                    ? 'bg-emerald-50 border-l-2 border-l-emerald-500'
                    : 'hover:bg-slate-50'
                }`}
              >
                <div className="font-semibold text-slate-800 truncate">{vc.vcn}</div>
                <div className="text-slate-500 truncate">{vc.vessel_name}</div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* ── RIGHT: Journey Detail ─────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-50">
        {!selectedVcId ? (
          <div className="flex-1 flex items-center justify-center text-sm text-slate-400">
            Select a vessel call to view its journey reconstruction.
          </div>
        ) : loadingJourney ? (
          <div className="flex-1 flex items-center justify-center text-sm text-slate-400">
            Loading journey…
          </div>
        ) : error && !journey ? (
          <div className="p-6">
            <p className="text-sm text-red-600 mb-3">{error}</p>
            <button
              onClick={handleReconstruct}
              disabled={reconstructing}
              className="px-3 py-1.5 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700 disabled:opacity-50"
            >
              {reconstructing ? 'Reconstructing…' : 'Reconstruct Journey'}
            </button>
          </div>
        ) : journey ? (
          <>
            {/* Header */}
            <div className="bg-white border-b border-slate-200 px-5 py-3 flex items-start justify-between gap-4 flex-shrink-0">
              <div>
                <h1 className="text-sm font-bold text-slate-900">
                  {journey.vcn} — {journey.vessel_name}
                </h1>
                <div className="flex gap-3 mt-1 flex-wrap">
                  <span className="text-[10px] text-slate-500">
                    Status:{' '}
                    <span
                      className={`font-semibold ${journey.status === 'RECONSTRUCTED' ? 'text-emerald-700' : 'text-amber-700'}`}
                    >
                      {journey.status}
                    </span>
                  </span>
                  <span className="text-[10px] text-slate-500">
                    Version: <span className="font-semibold">{journey.reconstruction_version}</span>
                  </span>
                  <span className="text-[10px] text-slate-500">
                    Rule: <span className="font-semibold">{journey.rule_version ?? '—'}</span>
                  </span>
                  <span className="text-[10px] text-slate-500">
                    Computed: <span className="font-semibold">{fmtTs(journey.computed_at)}</span>
                  </span>
                </div>
                {journey.coverage_summary && (
                  <div className="flex gap-3 mt-1 flex-wrap">
                    <span className="text-[10px] text-slate-400">
                      Stages: {journey.coverage_summary.stages_available} available /{' '}
                      {journey.coverage_summary.stages_missing} missing /{' '}
                      {journey.coverage_summary.stages_inferred} inferred /{' '}
                      {journey.coverage_summary.stages_total} total
                    </span>
                    {journey.coverage_summary.shifting_occurrences > 0 && (
                      <span className="text-[10px] text-amber-700 font-semibold">
                        ⇄ {journey.coverage_summary.shifting_occurrences} shift(s)
                      </span>
                    )}
                    {conflicts.filter((c) => c.conflict_detected).length > 0 && (
                      <span className="text-[10px] text-red-700 font-semibold">
                        ⚠ {conflicts.filter((c) => c.conflict_detected).length} observation conflict(s)
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {reconstructMsg && (
                  <span className="text-[10px] text-emerald-700">{reconstructMsg}</span>
                )}
                <button
                  onClick={handleReconstruct}
                  disabled={reconstructing}
                  className="px-3 py-1.5 bg-emerald-600 text-white text-[11px] font-semibold rounded hover:bg-emerald-700 disabled:opacity-50"
                >
                  {reconstructing ? 'Reconstructing…' : '↺ Reconstruct'}
                </button>
              </div>
            </div>

            {/* Tabs */}
            <div className="bg-white border-b border-slate-200 px-5 flex gap-1 flex-shrink-0">
              {(
                [
                  { id: 'timeline', label: 'Timeline' },
                  { id: 'decomposition', label: 'Time Decomposition' },
                  { id: 'conflicts', label: `Conflicts (${conflicts.filter((c) => c.conflict_detected).length})` },
                  { id: 'history', label: 'History' },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setTab(t.id)
                    if (t.id === 'history') handleLoadHistory()
                  }}
                  className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                    tab === t.id
                      ? 'border-emerald-500 text-emerald-700'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* ── Timeline ── */}
              {tab === 'timeline' && (
                <div className="space-y-1">
                  {journey.stages.map((s, i) => (
                    <div
                      key={s.id}
                      className={`rounded border px-3 py-2 text-xs ${
                        s.availability !== 'AVAILABLE'
                          ? 'border-slate-200 bg-white opacity-60'
                          : s.deviation_type === 'SEQUENCE_VIOLATION'
                          ? 'border-red-200 bg-red-50'
                          : 'border-slate-200 bg-white'
                      }`}
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] text-slate-400 w-5 text-right">{i + 1}</span>
                        <span className="font-semibold text-slate-800 flex-1 min-w-0 truncate">
                          {s.stage_name}
                          {s.shift_occurrence_index > 0 && (
                            <span className="ml-1 text-amber-600 font-normal">
                              #{s.shift_occurrence_index}
                            </span>
                          )}
                        </span>
                        {availabilityBadge(s)}
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${categoryColor(s.time_category)}`}
                        >
                          {s.time_category.replace('_', ' ')}
                        </span>
                      </div>
                      {s.availability === 'AVAILABLE' && (
                        <div className="flex gap-3 mt-1 ml-7 flex-wrap text-[10px] text-slate-500">
                          <span>Start: {fmtTs(s.start_time)}</span>
                          <span>End: {fmtTs(s.end_time)}</span>
                          <span className="font-semibold text-slate-700">Duration: {fmt(s.duration_hours)}</span>
                          {s.deviation_type === 'SEQUENCE_VIOLATION' && (
                            <span className="text-red-600 font-semibold">
                              ⚠ {s.deviation_detail?.description}
                            </span>
                          )}
                        </div>
                      )}
                      {s.availability !== 'AVAILABLE' && s.inference_reason && (
                        <div className="ml-7 mt-0.5 text-[10px] text-slate-400 italic">
                          {s.inference_reason}
                        </div>
                      )}
                      {s.is_inferred && s.inference_reason && (
                        <div className="ml-7 mt-0.5 text-[10px] text-purple-600 italic">
                          ⓘ Inferred: {s.inference_reason}
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Handovers */}
                  {journey.handovers.filter((h) => h.status === 'AVAILABLE').length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-200">
                      <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wide mb-2">
                        Stakeholder Handovers
                      </h3>
                      <div className="space-y-1">
                        {journey.handovers
                          .filter((h) => h.status === 'AVAILABLE')
                          .map((h, i) => (
                            <div
                              key={i}
                              className="rounded border border-sky-100 bg-sky-50 px-3 py-1.5 text-[10px] text-slate-600 flex gap-3 flex-wrap"
                            >
                              <span>
                                <span className="font-semibold">{h.from_actor ?? '—'}</span>
                                {' → '}
                                <span className="font-semibold">{h.to_actor ?? '—'}</span>
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
                    <div className="mt-4 pt-4 border-t border-slate-200">
                      <h3 className="text-xs font-bold text-red-700 uppercase tracking-wide mb-2">
                        Operational Deviations
                      </h3>
                      <div className="space-y-1">
                        {journey.deviation_report.map((d, i) => (
                          <div
                            key={i}
                            className="rounded border border-red-200 bg-red-50 px-3 py-1.5 text-[10px] text-red-800"
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
                <div className="bg-white rounded border border-slate-200 p-4">
                  {journey.time_decomposition && journey.time_decomposition.status === 'AVAILABLE' ? (
                    <>
                      <h3 className="text-xs font-bold text-slate-700 mb-3">
                        Active / Wait / Hold / Delay / Unclassified Decomposition
                      </h3>
                      <DecompositionBar d={journey.time_decomposition} />
                      <table className="mt-4 w-full text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-200">
                            <th className="text-left py-1.5 text-slate-500 font-semibold">Category</th>
                            <th className="text-right py-1.5 text-slate-500 font-semibold">Hours</th>
                            <th className="text-right py-1.5 text-slate-500 font-semibold">%</th>
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
                                <tr key={cat} className="border-b border-slate-100">
                                  <td className="py-1.5">
                                    <span
                                      className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${categoryColor(cat)}`}
                                    >
                                      {cat.replace('_', ' ')}
                                    </span>
                                  </td>
                                  <td className="text-right text-slate-700 font-mono">{fmt(val)}</td>
                                  <td className="text-right text-slate-500">{pct}%</td>
                                </tr>
                              )
                            }
                          )}
                          <tr className="font-semibold text-slate-800">
                            <td className="py-2">Total</td>
                            <td className="text-right font-mono">
                              {fmt(journey.time_decomposition.total_hours)}
                            </td>
                            <td className="text-right">100%</td>
                          </tr>
                        </tbody>
                      </table>
                      <p className="mt-3 text-[10px] text-slate-400 italic">
                        Components are non-overlapping. Shifting time is carved out of the containing
                        stage's bucket and recorded under DELAY.
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-slate-500 italic">
                      Time decomposition is UNAVAILABLE — insufficient stage data to compute.
                    </p>
                  )}
                </div>
              )}

              {/* ── Conflicts ── */}
              {tab === 'conflicts' && (
                <div className="space-y-3">
                  {conflicts.filter((c) => c.conflict_detected).length === 0 ? (
                    <p className="text-sm text-slate-500 italic">
                      No observation conflicts detected for this vessel call.
                    </p>
                  ) : (
                    conflicts
                      .filter((c) => c.conflict_detected)
                      .map((c) => (
                        <div
                          key={c.id}
                          className="bg-white rounded border border-amber-200 px-4 py-3 text-xs"
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold text-[10px]">
                              CONFLICT
                            </span>
                            <span className="font-semibold text-slate-700">
                              Event Definition: {c.event_definition_id.slice(0, 8)}…
                            </span>
                            <span className="text-slate-400 text-[10px]">
                              Method: {c.selection_method}
                            </span>
                          </div>
                          {c.selection_reasoning?.comparison && (
                            <div className="space-y-1 mt-2">
                              <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-wide">
                                Competing observations — all retained, none deleted:
                              </p>
                              {c.selection_reasoning.comparison.map((obs) => (
                                <div
                                  key={obs.event_occurrence_id}
                                  className={`rounded px-2 py-1 flex gap-3 flex-wrap text-[10px] ${
                                    obs.selected
                                      ? 'bg-emerald-50 border border-emerald-200'
                                      : 'bg-slate-50 border border-slate-200'
                                  }`}
                                >
                                  <span className="font-mono text-slate-500">
                                    {obs.event_occurrence_id.slice(0, 8)}…
                                  </span>
                                  <span>Source: <strong>{obs.source_system}</strong></span>
                                  <span>Verification: <strong>{obs.verification_status}</strong></span>
                                  <span>Confidence: {obs.confidence}</span>
                                  <span>UTC: {fmtTs(obs.utc_value)}</span>
                                  {obs.selected && (
                                    <span className="font-semibold text-emerald-700">✓ CANONICAL</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                          {c.selection_reasoning?.winning_reason && (
                            <p className="mt-2 text-[10px] text-slate-500 italic">
                              Selection rationale: {c.selection_reasoning.winning_reason}
                            </p>
                          )}
                          <p className="mt-1.5 text-[10px] text-slate-400">
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
                    <p className="text-sm text-slate-400">Loading history…</p>
                  ) : historyRows.length === 0 ? (
                    <p className="text-sm text-slate-500 italic">No reconstruction history yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {historyRows.map((h) => (
                        <div
                          key={h.run_version}
                          className="bg-white rounded border border-slate-200 px-4 py-2.5 text-xs"
                        >
                          <div className="flex items-center gap-3">
                            <span className="font-semibold text-slate-700">v{h.run_version}</span>
                            <span className="text-slate-400">Rule: {h.rule_version ?? '—'}</span>
                            <span className="text-slate-400">Trigger: {h.triggered_by}</span>
                            <span className="text-slate-400 ml-auto">{fmtTs(h.created_at)}</span>
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
