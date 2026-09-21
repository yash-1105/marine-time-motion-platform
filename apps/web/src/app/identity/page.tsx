'use client'

import React, { useState, useEffect } from 'react'
import { useAuth } from '../../lib/auth-context'
import { PageHeader, SectionHeader, Card, KpiCard, StatusBadge, EmptyState, LoadingState, FilterChip } from '@/components/ui'
import { TriangleAlert } from 'lucide-react'

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
  const { can, token: authToken, isLoading: authLoading } = useAuth()
  const [population, setPopulation] = useState<PopulationSummary | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [decisions, setDecisions] = useState<MergeDecisionItem[]>([])
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [candidateDetail, setCandidateDetail] = useState<CandidateDetail | null>(null)
  const [preview, setPreview] = useState<MergePreview | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [initialLoad, setInitialLoad] = useState<boolean>(true)

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  const API_URL = API_BASE.endsWith('/api/v1') ? API_BASE : `${API_BASE}/api/v1`

  const fetchData = React.useCallback(async () => {
    try {
      setLoading(true)
      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken || 'dev-token'}`,
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
      setInitialLoad(false)
    }
  }, [API_URL, authToken])

  useEffect(() => {
    if (authLoading) return
    fetchData()
  }, [authLoading, fetchData])

  const handleSelectCandidate = async (id: string) => {
    setSelectedCandidateId(id)
    try {
      const headers = { Authorization: `Bearer ${authToken || 'dev-token'}` }

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
      const res = await fetch(`${API_URL}/identity/resolve?auto_merge=true`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken || 'dev-token'}`,
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
      const res = await fetch(`${API_URL}/identity/merge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken || 'dev-token'}`,
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
      const res = await fetch(`${API_URL}/identity/unmerge/${decisionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken || 'dev-token'}`,
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

  if (initialLoad && loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Identity & Merges"
        />
        <LoadingState label="Loading identity resolution data…" />
      </div>
    )
  }

  return (
    <div className="min-h-full space-y-6 bg-[var(--color-bg)] px-6 pb-8 lg:px-8">
      <PageHeader
        title="Identity & Merges"
        className="-mx-6 lg:-mx-8"
        actions={
          can('merge') && (
            <button
              onClick={handleResolveAndAutoMerge}
              disabled={loading}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer"
            >
              {loading ? 'Processing…' : 'Scan & Auto-Merge Candidates'}
            </button>
          )
        }
      />

      {/* Status Feedback Message */}
      {message && (
        <div
          className={`p-3 rounded-md text-sm border ${
            message.type === 'success'
              ? 'bg-[var(--color-good-bg)] border-[var(--color-good-border)] text-[var(--color-good)]'
              : 'bg-[var(--color-critical-bg)] border-[var(--color-critical-border)] text-[var(--color-critical)]'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Population & KPI Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Total Raw Rows"
          value={population?.total_rows ?? 74}
          context="Includes intentional fixture duplicates"
        />

        <KpiCard
          label="Merged Duplicates"
          value={population?.merged_rows ?? 2}
          context="Consolidated via survivorship"
        />

        <KpiCard
          label="Base Population"
          value={population?.consolidated_base_population ?? 72}
          status={population?.reconciled ? 'RECONCILED' : 'PENDING'}
          tone={population?.reconciled ? 'good' : 'neutral'}
          context={
            population?.reconciled
              ? `Reconciled to ${population?.target_base_population ?? 72} base calls`
              : `Target: ${population?.target_base_population ?? 72} base calls`
          }
        />

        <KpiCard
          label="Active Candidates"
          value={candidates.length}
          context="Evaluated pairwise with evidence"
        />
      </div>

      {/* Main Section: Candidates & Evidence Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Candidates Table (7 cols) */}
        <Card className="lg:col-span-7" padded={false}>
          <div className="p-4 border-b border-[var(--color-border)] flex items-center justify-between flex-wrap gap-2">
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              Candidate Pairs ({filteredCandidates.length})
            </span>
            <FilterChip
              ariaLabel="Filter candidate pairs"
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { value: 'ALL', label: 'All Pairs' },
                { value: 'AUTO_MERGE_CANDIDATE', label: 'Auto-Merge (≥ 0.98)' },
                { value: 'STEWARD_REVIEW', label: 'Review Queue (0.85–0.97)' },
                { value: 'MERGED', label: 'Merged' },
                { value: 'CONFLICT', label: 'Blocked by Conflict' },
              ]}
            />
          </div>

          <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
            {filteredCandidates.length === 0 ? (
              <EmptyState
                title="No candidate pairs"
                description="No candidate pairs match the current filter."
              />
            ) : (
              <table className="w-full text-left text-sm border-collapse">
                <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] text-xs uppercase tracking-wide border-b border-[var(--color-border)] sticky top-0">
                  <tr>
                    <th className="p-3 font-medium">Candidate Records</th>
                    <th className="p-3 font-medium">Score</th>
                    <th className="p-3 font-medium">Type</th>
                    <th className="p-3 font-medium">Status</th>
                    <th className="p-3 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {filteredCandidates.map((c) => {
                    const isSelected = selectedCandidateId === c.id
                    return (
                      <tr
                        key={c.id}
                        onClick={() => handleSelectCandidate(c.id)}
                        className={`hover:bg-[var(--color-surface-muted)] cursor-pointer transition-colors ${
                          isSelected ? 'bg-[var(--color-accent-soft)]' : ''
                        }`}
                      >
                        <td className="p-3">
                          <div className="font-medium text-[var(--color-text-primary)] truncate max-w-[220px]">
                            {c.vessel_name_1}
                          </div>
                          <div className="text-xs text-[var(--color-text-secondary)] truncate max-w-[220px]">
                            vs {c.vessel_name_2}
                          </div>
                          <div className="text-xs text-[var(--color-text-tertiary)]">
                            {c.vcn_1 || 'No VCN'} {c.vcn_1 === c.vcn_2 ? '(Same VCN)' : `vs ${c.vcn_2 || 'No VCN'}`}
                          </div>
                        </td>

                        <td className="p-3">
                          <span
                            className={`font-mono font-semibold text-sm ${
                              c.match_score >= 0.98
                                ? 'text-[var(--color-good)]'
                                : c.match_score >= 0.85
                                ? 'text-[var(--color-warning)]'
                                : 'text-[var(--color-text-secondary)]'
                            }`}
                          >
                            {(c.match_score * 100).toFixed(1)}%
                          </span>
                        </td>

                        <td className="p-3">
                          <span className="text-xs uppercase font-medium px-2 py-0.5 rounded-md bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] border border-[var(--color-border)]">
                            {c.match_type || 'PROBABILISTIC'}
                          </span>
                        </td>

                        <td className="p-3">
                          {c.conflict_detected ? (
                            <StatusBadge label="Blocked Conflict" tone="critical" />
                          ) : c.status === 'MERGED' ? (
                            <StatusBadge label="Merged" tone="good" />
                          ) : c.status === 'AUTO_MERGE_CANDIDATE' ? (
                            <StatusBadge label="Auto-Merge" tone="good" />
                          ) : (
                            <StatusBadge label="Review Queue" tone="warning" />
                          )}
                        </td>

                        <td className="p-3 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleSelectCandidate(c.id)
                            }}
                            className="text-xs px-2.5 py-1.5 rounded-md bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] font-medium transition-colors cursor-pointer"
                          >
                            Evidence
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </Card>

        {/* Explainable Evidence & Merge Preview Drawer (5 cols) */}
        <Card className="lg:col-span-5" padded={false}>
          <div className="p-4 border-b border-[var(--color-border)]">
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              Explainable Match Evidence
            </span>
          </div>

          <div className="p-4 max-h-[520px] overflow-y-auto">
            {!candidateDetail ? (
              <EmptyState
                title="No candidate selected"
                description="Select a candidate pair from the list to view attribute-level explainable scoring and survivorship preview."
              />
            ) : (
              <div className="space-y-4">
                {/* Pair Overview */}
                <div className="p-3 bg-[var(--color-surface-muted)] border border-[var(--color-border)] rounded-md text-sm space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[var(--color-text-secondary)]">Overall Match Score</span>
                    <span className="font-mono font-semibold text-[var(--color-good)] text-base">
                      {(candidateDetail.match_score * 100).toFixed(1)}%
                    </span>
                  </div>

                  {candidateDetail.conflict_detected && (
                    <div className="p-2.5 bg-[var(--color-critical-bg)] border border-[var(--color-critical-border)] rounded-md text-[var(--color-critical)] text-xs">
                      <div className="font-semibold flex items-center gap-1.5">
                        <TriangleAlert size={14} aria-hidden="true" /> Hard Rule Conflict: Auto-Merge Blocked
                      </div>
                      <ul className="list-disc list-inside mt-1 space-y-0.5">
                        {candidateDetail.conflict_reasons?.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1 text-sm">
                    <span className="text-[var(--color-text-secondary)]">Candidate Status</span>
                    <StatusBadge status={candidateDetail.status} />
                  </div>
                </div>

                {/* Explainable Attribute Breakdown */}
                <div>
                  <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
                    Attribute Scoring Breakdown
                  </h3>
                  <div className="space-y-2">
                    {candidateDetail.evidence_breakdown?.map((ev, idx) => (
                      <div
                        key={idx}
                        className="p-2.5 border border-[var(--color-border)] rounded-md text-xs bg-[var(--color-surface)]"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="font-medium capitalize text-[var(--color-text-primary)]">
                            {ev.attribute.replace('_', ' ')}
                          </span>
                          <div className="flex items-center gap-2">
                            <StatusBadge
                              label={ev.agreement}
                              showGlyph={false}
                              tone={
                                ev.agreement === 'AGREED'
                                  ? 'good'
                                  : ev.agreement === 'PARTIAL'
                                  ? 'warning'
                                  : ev.agreement === 'DISAGREED'
                                  ? 'critical'
                                  : 'neutral'
                              }
                            />
                            <span className="font-mono text-[var(--color-good)] font-semibold">
                              +{ev.contribution.toFixed(2)}
                            </span>
                          </div>
                        </div>
                        <div className="text-xs text-[var(--color-text-secondary)] mt-1">{ev.explanation}</div>
                        <div className="mt-1.5 flex items-center gap-2 text-xs text-[var(--color-text-tertiary)] font-mono">
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
                    <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
                      Consolidated Preview (Survivorship)
                    </h3>
                    <div className="max-h-48 overflow-y-auto border border-[var(--color-border)] rounded-md text-xs">
                      <table className="w-full text-left">
                        <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] sticky top-0 text-xs uppercase tracking-wide">
                          <tr>
                            <th className="p-2">Field</th>
                            <th className="p-2">Consolidated Value</th>
                            <th className="p-2">Rule Applied</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--color-border)]">
                          {preview.field_comparisons
                            ?.filter((fc) => fc.consolidated_value !== null)
                            .map((fc, i) => (
                              <tr key={i}>
                                <td className="p-2 font-medium text-[var(--color-text-primary)]">{fc.label}</td>
                                <td className="p-2 font-mono text-[var(--color-good)]">
                                  {String(fc.consolidated_value)}
                                </td>
                                <td className="p-2 text-[var(--color-text-tertiary)]">{fc.rule_applied}</td>
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
                    className="w-full py-2.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    Commit Merge (Absorb Duplicate)
                  </button>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Merge Decisions & Safe Unmerge Audit History */}
      <Card padded={false}>
        <div className="p-4 border-b border-[var(--color-border)] flex items-center justify-between flex-wrap gap-2">
          <SectionHeader title="Merge Decisions & Unmerge Audit History" className="mb-0" />
          <span className="text-sm text-[var(--color-text-secondary)] font-medium">
            Decisions: {decisions.length}
          </span>
        </div>

        {decisions.length === 0 ? (
          <EmptyState title="No merge decisions" description="No merge decisions recorded yet." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] text-xs uppercase tracking-wide border-b border-[var(--color-border)]">
                <tr>
                  <th className="p-3 font-medium">Decision ID</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Survivor Record ID</th>
                  <th className="p-3 font-medium">Merged Record ID</th>
                  <th className="p-3 font-medium">Actor</th>
                  <th className="p-3 font-medium">Timestamp</th>
                  <th className="p-3 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {decisions.map((d) => (
                  <tr key={d.id} className="hover:bg-[var(--color-surface-muted)] transition-colors">
                    <td className="p-3 font-mono text-xs text-[var(--color-text-secondary)]">{d.id.slice(0, 8)}...</td>
                    <td className="p-3">
                      <StatusBadge
                        label={d.decision}
                        showGlyph={false}
                        tone={d.decision === 'MERGED' ? 'good' : 'neutral'}
                      />
                    </td>
                    <td className="p-3 font-mono text-xs text-[var(--color-text-primary)]">
                      {d.survivor_record_id?.slice(0, 8)}...
                    </td>
                    <td className="p-3 font-mono text-xs text-[var(--color-text-secondary)]">
                      {d.merged_record_id?.slice(0, 8)}...
                    </td>
                    <td className="p-3 text-[var(--color-text-secondary)]">{d.actor}</td>
                    <td className="p-3 text-[var(--color-text-tertiary)] text-xs">
                      {d.created_at ? new Date(d.created_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="p-3 text-right">
                      {can('unmerge') && d.decision === 'MERGED' && (
                        <button
                          onClick={() => handleUnmerge(d.id)}
                          disabled={loading}
                          className="px-2.5 py-1.5 text-xs rounded-md bg-[var(--color-warning-bg)] hover:opacity-80 text-[var(--color-warning)] border border-[var(--color-warning-border)] font-medium transition-opacity disabled:opacity-50 cursor-pointer"
                        >
                          Safe Unmerge
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
