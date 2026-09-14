'use client'

import React, { useState, useEffect } from 'react'
import { useAuth } from '../../lib/auth-context'

interface Candidate {
  id: string
  source_record_1_id: string
  source_record_2_id: string
  vessel_name_1: string
  vessel_name_2: string
  vcn_1?: string
  vcn_2?: string
  match_score: number
  status: string
  match_type?: string
  conflict_detected: boolean
  conflict_reasons?: string[]
}

interface EvidenceItem {
  attribute: string
  record_1_value?: string
  record_2_value?: string
  agreement: string
  weight: number
  contribution: number
  explanation: string
}

interface CandidateDetail extends Candidate {
  evidence_breakdown: EvidenceItem[]
}

interface FieldComparison {
  field: string
  label: string
  record_1_value: string | number | null
  record_2_value: string | number | null
  consolidated_value: string | number | null
  winning_record_id: string
  rule_applied: string
  provenance: string
}

interface MergePreview {
  survivor_id: string
  merged_id: string
  survivor_vcn: string
  merged_vcn: string
  field_comparisons: FieldComparison[]
  consolidated_preview: Record<string, string | number | null>
}

interface MergeDecisionItem {
  id: string
  decision: string
  is_reversible: boolean
  survivor_record_id: string
  merged_record_id: string
  actor: string
  created_at: string
  notes?: string
}

interface PopulationSummary {
  total_rows: number
  merged_rows: number
  consolidated_base_population: number
  target_base_population: number
  reconciled: boolean
}

export default function IdentityPage() {
  const { can } = useAuth()
  const [population, setPopulation] = useState<PopulationSummary | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [decisions, setDecisions] = useState<MergeDecisionItem[]>([])
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [candidateDetail, setCandidateDetail] = useState<CandidateDetail | null>(null)
  const [preview, setPreview] = useState<MergePreview | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

  const fetchData = React.useCallback(async () => {
    try {
      setLoading(true)
      const token = localStorage.getItem('token') || ''
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      }

      // 1. Population summary
      const popRes = await fetch(`${API_URL}/identity/population?tenant_id=synthetic-tenant`, { headers })
      if (popRes.ok) {
        const popData = await popRes.json()
        setPopulation(popData)
      }

      // 2. Candidates
      const candRes = await fetch(`${API_URL}/identity/candidates?limit=100`, { headers })
      if (candRes.ok) {
        const candData = await candRes.json()
        setCandidates(candData.items || [])
      }

      // 3. Decisions
      const decRes = await fetch(`${API_URL}/identity/decisions`, { headers })
      if (decRes.ok) {
        const decData = await decRes.json()
        setDecisions(decData || [])
      }
    } catch (error) {
      console.error('Failed to fetch identity data:', error)
    } finally {
      setLoading(false)
    }
  }, [API_URL])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSelectCandidate = async (id: string) => {
    setSelectedCandidateId(id)
    try {
      const token = localStorage.getItem('token') || ''
      const headers = { Authorization: `Bearer ${token}` }

      const detailRes = await fetch(`${API_URL}/identity/candidates/${id}`, { headers })
      if (detailRes.ok) {
        const detailData = await detailRes.json()
        setCandidateDetail(detailData)
      }

      const prevRes = await fetch(`${API_URL}/identity/preview/${id}`, { headers })
      if (prevRes.ok) {
        const prevData = await prevRes.json()
        setPreview(prevData)
      }
    } catch (error) {
      console.error('Failed to fetch candidate details:', error)
    }
  }

  const handleResolveAndAutoMerge = async () => {
    try {
      setLoading(true)
      setMessage(null)
      const token = localStorage.getItem('token') || ''
      const res = await fetch(`${API_URL}/identity/resolve?auto_merge=true`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        const data = await res.json()
        setMessage({
          text: `Identity Resolution completed: ${data.total_candidates_found} candidate pairs evaluated, ${data.auto_merged_count} merged. Base population: ${data.consolidated_base_population}.`,
          type: 'success',
        })
        fetchData()
      } else {
        const err = await res.json()
        setMessage({ text: err.detail || 'Identity resolution failed', type: 'error' })
      }
    } catch (error) {
      const e = error as Error
      setMessage({ text: e.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleMerge = async (candidateId: string) => {
    try {
      setLoading(true)
      const token = localStorage.getItem('token') || ''
      const res = await fetch(`${API_URL}/identity/merge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ candidate_id: candidateId }),
      })
      if (res.ok) {
        setMessage({ text: 'Vessel calls merged successfully with prior state snapshotted.', type: 'success' })
        fetchData()
        if (selectedCandidateId === candidateId) {
          handleSelectCandidate(candidateId)
        }
      } else {
        const err = await res.json()
        setMessage({ text: err.detail || 'Merge rejected by rule engine', type: 'error' })
      }
    } catch (error) {
      const e = error as Error
      setMessage({ text: e.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handleUnmerge = async (decisionId: string) => {
    try {
      setLoading(true)
      const token = localStorage.getItem('token') || ''
      const res = await fetch(`${API_URL}/identity/unmerge/${decisionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ notes: 'Manual steward unmerge' }),
      })
      if (res.ok) {
        setMessage({ text: 'Vessel calls unmerged successfully. Original records and child data restored.', type: 'success' })
        fetchData()
        setSelectedCandidateId(null)
      } else {
        const err = await res.json()
        setMessage({ text: err.detail || 'Unmerge failed', type: 'error' })
      }
    } catch (error) {
      const e = error as Error
      setMessage({ text: e.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const filteredCandidates = candidates.filter((c) => {
    if (statusFilter === 'ALL') return true
    if (statusFilter === 'CONFLICT') return c.conflict_detected
    return c.status === statusFilter
  })

  return (
    <div className="space-y-6">
      {/* Header & Title */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Identity Resolution &amp; Merge</h1>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic and probabilistic matching, explainable scoring evidence, survivorship preview, and safe unmerge.
          </p>
        </div>

        {can('merge') && (
          <button
            onClick={handleResolveAndAutoMerge}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
          >
            {loading ? 'Processing...' : '⚡ Scan & Auto-Merge Candidates'}
          </button>
        )}
      </div>

      {/* Status Feedback Message */}
      {message && (
        <div
          className={`p-3 rounded text-xs border ${
            message.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Population & KPI Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 bg-white rounded border border-slate-200 shadow-xs">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total Raw Rows</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{population?.total_rows ?? 74}</div>
          <div className="text-[11px] text-slate-400 mt-1">Includes intentional fixture duplicates</div>
        </div>

        <div className="p-4 bg-white rounded border border-slate-200 shadow-xs">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Merged Duplicates</div>
          <div className="text-2xl font-bold text-amber-600 mt-1">{population?.merged_rows ?? 2}</div>
          <div className="text-[11px] text-slate-400 mt-1">Consolidated via survivorship</div>
        </div>

        <div className="p-4 bg-white rounded border border-slate-200 shadow-xs">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Base Population</div>
          <div className="text-2xl font-bold text-emerald-600 mt-1">
            {population?.consolidated_base_population ?? 72}
          </div>
          <div className="text-[11px] text-emerald-700 font-medium mt-1">
            {population?.reconciled ? '✓ Reconciled to 72 base calls' : 'Target: 72 base calls'}
          </div>
        </div>

        <div className="p-4 bg-white rounded border border-slate-200 shadow-xs">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Active Candidates</div>
          <div className="text-2xl font-bold text-blue-600 mt-1">{candidates.length}</div>
          <div className="text-[11px] text-slate-400 mt-1">Evaluated pairwise with evidence</div>
        </div>
      </div>

      {/* Main Section: Candidates & Evidence Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Candidates Table (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded border border-slate-200 shadow-xs flex flex-col">
          <div className="p-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
            <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
              Candidate Pairs ({filteredCandidates.length})
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-500">Filter:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-xs border border-slate-300 rounded px-2 py-0.5 bg-white text-slate-700 font-medium"
              >
                <option value="ALL">All Pairs</option>
                <option value="AUTO_MERGE_CANDIDATE">Auto-Merge (≥0.98)</option>
                <option value="STEWARD_REVIEW">Review Queue (0.85–0.97)</option>
                <option value="MERGED">Merged</option>
                <option value="CONFLICT">Blocked by Conflict</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto flex-1 max-h-[500px]">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-100 text-slate-600 text-[11px] uppercase tracking-wider border-b border-slate-200 sticky top-0">
                <tr>
                  <th className="p-2.5 font-semibold">Candidate Records</th>
                  <th className="p-2.5 font-semibold">Score</th>
                  <th className="p-2.5 font-semibold">Type</th>
                  <th className="p-2.5 font-semibold">Status</th>
                  <th className="p-2.5 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredCandidates.map((c) => {
                  const isSelected = selectedCandidateId === c.id
                  return (
                    <tr
                      key={c.id}
                      onClick={() => handleSelectCandidate(c.id)}
                      className={`hover:bg-slate-50 cursor-pointer transition-colors ${
                        isSelected ? 'bg-emerald-50/70' : ''
                      }`}
                    >
                      <td className="p-2.5">
                        <div className="font-semibold text-slate-900 truncate max-w-[200px]">
                          {c.vessel_name_1}
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono truncate max-w-[200px]">
                          vs {c.vessel_name_2}
                        </div>
                        <div className="text-[10px] text-slate-400">
                          {c.vcn_1 || 'No VCN'} {c.vcn_1 === c.vcn_2 ? '(Same VCN)' : `vs ${c.vcn_2 || 'No VCN'}`}
                        </div>
                      </td>

                      <td className="p-2.5">
                        <span
                          className={`font-mono font-bold text-xs ${
                            c.match_score >= 0.98
                              ? 'text-emerald-700'
                              : c.match_score >= 0.85
                              ? 'text-amber-700'
                              : 'text-slate-600'
                          }`}
                        >
                          {(c.match_score * 100).toFixed(1)}%
                        </span>
                      </td>

                      <td className="p-2.5">
                        <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                          {c.match_type || 'PROBABILISTIC'}
                        </span>
                      </td>

                      <td className="p-2.5">
                        {c.conflict_detected ? (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-100 text-red-700">
                            BLOCKED CONFLICT
                          </span>
                        ) : c.status === 'MERGED' ? (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                            MERGED
                          </span>
                        ) : c.status === 'AUTO_MERGE_CANDIDATE' ? (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">
                            AUTO-MERGE
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                            REVIEW QUEUE
                          </span>
                        )}
                      </td>

                      <td className="p-2.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSelectCandidate(c.id)
                          }}
                          className="text-[11px] px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium"
                        >
                          Evidence
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Explainable Evidence & Merge Preview Drawer (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded border border-slate-200 shadow-xs flex flex-col">
          <div className="p-3 border-b border-slate-200 bg-slate-50">
            <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
              Explainable Match Evidence
            </span>
          </div>

          <div className="p-4 flex-1 overflow-y-auto max-h-[500px]">
            {!candidateDetail ? (
              <div className="py-12 text-center text-xs text-slate-400">
                Select a candidate pair from the list to view attribute-level explainable scoring and survivorship preview.
              </div>
            ) : (
              <div className="space-y-4">
                {/* Pair Overview */}
                <div className="p-3 bg-slate-50 border border-slate-200 rounded text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-700">Overall Match Score:</span>
                    <span className="font-mono font-bold text-emerald-700 text-sm">
                      {(candidateDetail.match_score * 100).toFixed(1)}%
                    </span>
                  </div>

                  {candidateDetail.conflict_detected && (
                    <div className="p-2 bg-red-50 border border-red-200 rounded text-red-800 text-[11px]">
                      <div className="font-bold">⚠️ Hard Rule Conflict: Auto-Merge Blocked</div>
                      <ul className="list-disc list-inside mt-1">
                        {candidateDetail.conflict_reasons?.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-slate-500">Candidate Status:</span>
                    <span className="font-semibold">{candidateDetail.status}</span>
                  </div>
                </div>

                {/* Explainable Attribute Breakdown */}
                <div>
                  <h3 className="text-xs font-bold text-slate-700 mb-2">Attribute Scoring Breakdown</h3>
                  <div className="space-y-2">
                    {candidateDetail.evidence_breakdown?.map((ev, idx) => (
                      <div key={idx} className="p-2 border border-slate-200 rounded text-[11px] bg-white">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold capitalize text-slate-800">
                            {ev.attribute.replace('_', ' ')}
                          </span>
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                ev.agreement === 'AGREED'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : ev.agreement === 'PARTIAL'
                                  ? 'bg-amber-100 text-amber-800'
                                  : ev.agreement === 'DISAGREED'
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {ev.agreement}
                            </span>
                            <span className="font-mono text-emerald-700 font-bold">
                              +{ev.contribution.toFixed(2)}
                            </span>
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-500 mt-1">{ev.explanation}</div>
                        <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                          <span>R1: {ev.record_1_value || 'None'}</span>
                          <span>|</span>
                          <span>R2: {ev.record_2_value || 'None'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Survivorship Preview */}
                {preview && (
                  <div className="pt-2">
                    <h3 className="text-xs font-bold text-slate-700 mb-2">Consolidated Preview (Survivorship)</h3>
                    <div className="max-h-40 overflow-y-auto border border-slate-200 rounded text-[11px]">
                      <table className="w-full text-left">
                        <thead className="bg-slate-100 text-slate-600 sticky top-0 text-[10px]">
                          <tr>
                            <th className="p-1.5">Field</th>
                            <th className="p-1.5">Consolidated Value</th>
                            <th className="p-1.5">Rule Applied</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {preview.field_comparisons
                            ?.filter((fc) => fc.consolidated_value !== null)
                            .map((fc, i) => (
                              <tr key={i}>
                                <td className="p-1.5 font-medium text-slate-700">{fc.label}</td>
                                <td className="p-1.5 font-mono text-emerald-700">{String(fc.consolidated_value)}</td>
                                <td className="p-1.5 text-[10px] text-slate-400">{fc.rule_applied}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Actions */}
                {can('merge') && candidateDetail.status !== 'MERGED' && (
                  <button
                    onClick={() => handleMerge(candidateDetail.id)}
                    disabled={loading || candidateDetail.conflict_detected}
                    className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold transition-colors disabled:opacity-50"
                  >
                    Commit Merge (Absorb Duplicate)
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Merge Decisions & Safe Unmerge Audit History */}
      <div className="bg-white rounded border border-slate-200 shadow-xs">
        <div className="p-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
            Merge Decisions &amp; Unmerge Audit History
          </span>
          <span className="text-xs text-slate-500 font-medium">Decisions: {decisions.length}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-100 text-slate-600 text-[11px] uppercase tracking-wider border-b border-slate-200">
              <tr>
                <th className="p-3 font-semibold">Decision ID</th>
                <th className="p-3 font-semibold">Status</th>
                <th className="p-3 font-semibold">Survivor Record ID</th>
                <th className="p-3 font-semibold">Merged Record ID</th>
                <th className="p-3 font-semibold">Actor</th>
                <th className="p-3 font-semibold">Timestamp</th>
                <th className="p-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-4 text-center text-slate-400 text-xs">
                    No merge decisions recorded yet.
                  </td>
                </tr>
              ) : (
                decisions.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50 transition-colors">
                    <td className="p-3 font-mono text-[11px] text-slate-600">{d.id.slice(0, 8)}...</td>
                    <td className="p-3">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          d.decision === 'MERGED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {d.decision}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-700">{d.survivor_record_id?.slice(0, 8)}...</td>
                    <td className="p-3 font-mono text-[11px] text-slate-500">{d.merged_record_id?.slice(0, 8)}...</td>
                    <td className="p-3 text-slate-600">{d.actor}</td>
                    <td className="p-3 text-slate-500 text-[11px]">
                      {d.created_at ? new Date(d.created_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="p-3 text-right">
                      {can('unmerge') && d.decision === 'MERGED' && (
                        <button
                          onClick={() => handleUnmerge(d.id)}
                          disabled={loading}
                          className="px-2 py-1 text-xs rounded bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 font-semibold transition-colors disabled:opacity-50"
                        >
                          Safe Unmerge
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
