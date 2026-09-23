'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth-context'
import { RefreshCw, Search, X, Ban } from 'lucide-react'
import {
  PageHeader,
  KpiCard,
  StatusBadge,
  statusToTone,
  EmptyState,
  LoadingState,
  ErrorState,
  FilterChip,
} from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface QualityIssue {
  id: string
  rule_id: string
  vessel_call_id?: string | null
  record_reference: string
  issue_status: string
  rule_name?: string | null
  severity?: string | null
  scope?: string | null
  remediation_guidance?: string | null
  vcn?: string | null
  vessel_name?: string | null
  disposition?: string | null
  workflow_state?: string | null
  created_at?: string | null
  issue_class?: 'QUALITY' | 'OUTLIER'
  source_file?: string | null
  source_sheet?: string | null
  source_row?: number | null
  source_field?: string | null
  original_values?: Record<string, unknown> | null
  reason?: string | null
  movement_scope?: string | null
  service_type?: string | null
  is_excluded?: boolean
}

interface QualitySummary {
  total_issues: number
  open_issues: number
  resolved_issues: number
  critical_issues: number
  high_issues: number
  quarantined_calls_count: number
  total_active_calls: number
  clean_calls_count: number
  cleanliness_percentage: number
  by_severity: Record<string, number>
  total_rows?: number
  clean_rows?: number
  incomplete_rows?: number
  sequence_errors?: number
  duplicate_rows?: number
  outliers?: number
  excluded_rows?: number
  quarantined_rows?: number
}

const ISSUE_DESCRIPTIONS: Record<string, string> = {
  RULE_MANDATORY_ATA: 'Required actual arrival timestamp is missing.',
  RULE_ETA_BEFORE_ATA: 'Estimated arrival occurs after the actual arrival.',
  RULE_MISSING_SERVICE_EVENT: 'A required service event is missing.',
  RULE_PILOT_ON_BOARD_BEFORE_SCHEDULED: 'Pilot boarding time occurs before the pilot was scheduled.',
  RULE_DELAY_REASON: 'A delayed service is missing its required delay reason.',
  RULE_ORPHAN_EVENT: 'The event cannot be linked to a governed vessel call.',
  'DQ-001': 'Duplicate vessel call detected.',
  'DQ-002': 'Potential duplicate vessel call detected from an identifier variation.',
  'DQ-003': 'Required actual arrival timestamp is missing.',
  'DQ-004': 'Estimated arrival occurs after the actual arrival.',
  'DQ-005': 'A pilot request is missing its scheduled time.',
  'DQ-006': 'Invalid chronological sequence detected between anchorage arrival and pilot boarding.',
  'DQ-007': 'A delayed service is missing its required delay reason.',
  'DQ-010': 'Conflicting source timestamps exceed the governed tolerance.',
  'DQ-SERVICE-REQUEST-MISSING': 'Required service request timestamp is missing.',
  'DQ-SERVICE-SCHEDULE-MISSING': 'Required scheduled service timestamp is missing.',
  'DQ-SERVICE-SERVED-MISSING': 'Required actual or served timestamp is missing.',
  'DQ-SERVICE-SCHEDULE-BEFORE-REQUEST': 'Service was scheduled before it was requested.',
  'DQ-INVALID-TIMESTAMP': 'A source timestamp has an invalid date or time value.',
  'DQ-MISSING-MANDATORY-FIELD': 'A required source field is blank or missing.',
  'DQ-DUPLICATE-ROW': 'Duplicate source row detected.',
  'DQ-SEQUENCE-VIOLATION': 'Invalid chronological sequence detected.',
  OUTLIER: 'A governed statistical outlier was detected for review.',
}

function issueDescription(issue: QualityIssue) {
  return ISSUE_DESCRIPTIONS[issue.rule_id] || issue.reason || issue.remediation_guidance || issue.rule_name || 'Data quality rule violation detected.'
}

function DataQualityContent() {
  const { token, isLoading: authLoading } = useAuth()
  const searchParams = useSearchParams()

  const [summary, setSummary] = useState<QualitySummary | null>(null)
  const [issues, setIssues] = useState<QualityIssue[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>(searchParams.get('severity') || 'ALL')
  const [statusFilter, setStatusFilter] = useState<string>(searchParams.get('status') || 'ALL')
  const [ruleFilter, setRuleFilter] = useState<string>(searchParams.get('rule') || 'ALL')
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [fileFilter, setFileFilter] = useState<string>('ALL')
  const [serviceFilter, setServiceFilter] = useState<string>('ALL')
  const [movementFilter, setMovementFilter] = useState<string>('ALL')
  const [reviewFilter, setReviewFilter] = useState<string>('ALL')
  const [selectedIssueIds, setSelectedIssueIds] = useState<string[]>([])
  const [excludeReason, setExcludeReason] = useState('')
  const [excluding, setExcluding] = useState(false)

  // Resolve dialog state
  const [resolveTarget, setResolveTarget] = useState<QualityIssue | null>(null)
  const [resolutionNotes, setResolutionNotes] = useState<string>('')
  const [resolving, setResolving] = useState<boolean>(false)

  const headers = useMemo(() => ({ Authorization: `Bearer ${token || 'dev-token'}` }), [token])

  const fetchQualityData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryRes, issuesRes] = await Promise.all([
        fetch(`${API}/api/v1/quality/summary`, { headers }),
        fetch(`${API}/api/v1/quality/issues${reviewFilter === 'OUTLIERS' ? '?outliers_only=true' : reviewFilter === 'INCOMPLETE' ? '?incomplete_only=true' : reviewFilter === 'CHRONOLOGY' ? '?chronological_only=true' : ''}`, { headers }),
      ])

      if (summaryRes.ok) {
        const sumData = await summaryRes.json()
        setSummary(sumData)
      }
      if (issuesRes.ok) {
        const issData = await issuesRes.json()
        setIssues(Array.isArray(issData) ? issData : [])
      } else {
        throw new Error(`Failed to load quality issues: ${issuesRes.statusText}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error loading quality data')
    } finally {
      setLoading(false)
    }
  }, [headers, reviewFilter])

  useEffect(() => {
    if (authLoading) return
    fetchQualityData()
  }, [authLoading, fetchQualityData])

  const handleResolveIssue = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resolveTarget) return
    setResolving(true)
    try {
      const res = await fetch(`${API}/api/v1/quality/issues/${resolveTarget.id}/resolve`, {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          resolution_status: 'RESOLVED',
          notes: resolutionNotes || 'Resolved by Data Steward via operations portal',
        }),
      })
      if (res.ok) {
        setResolveTarget(null)
        setResolutionNotes('')
        fetchQualityData()
      } else {
        alert('Failed to resolve issue: ' + res.statusText)
      }
    } catch {
      alert('Network error while attempting resolution')
    } finally {
      setResolving(false)
    }
  }

  // Filtered issues
  const filteredIssues = useMemo(() => {
    return issues.filter((iss) => {
      if (severityFilter !== 'ALL' && (iss.severity || '').toUpperCase() !== severityFilter) {
        return false
      }
      if (statusFilter !== 'ALL' && (iss.issue_status || '').toUpperCase() !== statusFilter) {
        return false
      }
      if (ruleFilter !== 'ALL' && iss.rule_id !== ruleFilter) {
        return false
      }
      if (fileFilter !== 'ALL' && iss.source_file !== fileFilter) return false
      if (serviceFilter !== 'ALL' && iss.service_type !== serviceFilter) return false
      if (movementFilter !== 'ALL' && (iss.movement_scope || '').toUpperCase() !== movementFilter) return false
      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase().trim()
        const matchesVcn = (iss.vcn || '').toLowerCase().includes(q)
        const matchesName = (iss.vessel_name || '').toLowerCase().includes(q)
        const matchesRule = (iss.rule_id || '').toLowerCase().includes(q)
        const matchesExpr = (iss.rule_name || '').toLowerCase().includes(q)
        const matchesRef = (iss.record_reference || '').toLowerCase().includes(q)
        if (!matchesVcn && !matchesName && !matchesRule && !matchesExpr && !matchesRef) {
          return false
        }
      }
      return true
    })
  }, [issues, severityFilter, statusFilter, ruleFilter, fileFilter, serviceFilter, movementFilter, searchTerm])

  const distinctRules = useMemo(() => {
    const rules = new Set(issues.map((i) => i.rule_id))
    return Array.from(rules).sort()
  }, [issues])

  const hasActiveFilters = severityFilter !== 'ALL' || statusFilter !== 'ALL' || ruleFilter !== 'ALL'

  const distinctFiles = useMemo(() => Array.from(new Set(issues.map((i) => i.source_file).filter(Boolean) as string[])).sort(), [issues])
  const distinctServices = useMemo(() => Array.from(new Set(issues.map((i) => i.service_type).filter(Boolean) as string[])).sort(), [issues])

  const toggleSelected = (issueId: string) => {
    setSelectedIssueIds((current) => current.includes(issueId) ? current.filter((id) => id !== issueId) : [...current, issueId])
  }

  const excludeSelected = async () => {
    const selected = filteredIssues.filter((issue) => selectedIssueIds.includes(issue.id) && issue.issue_class !== 'OUTLIER')
    if (!selected.length || !excludeReason.trim()) return
    setExcluding(true)
    try {
      const response = await fetch(`${API}/api/v1/quality/exclusions`, {
        method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_ids: selected.map((issue) => issue.id), reason: excludeReason.trim() }),
      })
      if (!response.ok) throw new Error((await response.json()).message || response.statusText)
      setSelectedIssueIds([])
      setExcludeReason('')
      await fetchQualityData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to exclude selected source rows')
    } finally {
      setExcluding(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-full bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      <PageHeader
        title="Data Quality"
        meta={`${filteredIssues.length} issue${filteredIssues.length === 1 ? '' : 's'} shown`}
        actions={
          <button
            onClick={fetchQualityData}
            className="px-3 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw size={13} aria-hidden="true" /> Refresh Status
          </button>
        }
      />

      {/* KPI Summary */}
      {summary && (
        <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 flex-shrink-0">
          <KpiCard label="Total Rows" value={summary.total_rows ?? 0} context={<span>Current dataset staging</span>} />
          <KpiCard label="Clean Rows" value={summary.clean_rows ?? 0} tone="good" context={<span>Eligible source rows</span>} />
          <KpiCard
            label="Total Issues"
            value={summary.total_issues}
            context={<span>{summary.open_issues} active</span>}
          />
          <KpiCard label="Incomplete" value={summary.incomplete_rows ?? 0} context={<span>Missing governed inputs</span>} />
          <KpiCard label="Sequence Errors" value={summary.sequence_errors ?? 0} tone="warning" context={<span>DAG/service chronology</span>} />
          <KpiCard label="Duplicates" value={summary.duplicate_rows ?? 0} context={<span>Not double-counted</span>} />
          <KpiCard label="Outliers" value={summary.outliers ?? 0} context={<span>Review, not auto-deleted</span>} />
          <KpiCard label="Excluded" value={summary.excluded_rows ?? 0} context={<span>Audited analytical rows</span>} />
          <KpiCard
            label="Critical"
            value={summary.critical_issues}
            tone="critical"
            context={<span>Excluded from KPIs</span>}
          />
          <KpiCard
            label="High Severity"
            value={summary.high_issues}
            tone="warning"
            context={<span>Requires review</span>}
          />
          <KpiCard label="Warnings" value={(summary.by_severity?.MEDIUM || 0) + (summary.by_severity?.LOW || 0)} context={<span>Reviewable issues</span>} />
          <KpiCard
            label="Quarantined Calls"
            value={summary.quarantined_calls_count}
            context={<span>of {summary.total_active_calls} active calls</span>}
          />
          <KpiCard
            label="Clean Calls"
            value={summary.clean_calls_count}
            tone="good"
            context={<span>Zero DQ issues</span>}
          />
          <KpiCard
            label="Cleanliness Score"
            value={`${summary.cleanliness_percentage.toFixed(1)}%`}
            context={<span>Governed composite</span>}
          />
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-[var(--color-surface)] border-b border-[var(--color-border)] px-6 py-3 flex items-center justify-between gap-3 flex-wrap flex-shrink-0 text-xs">
        <div className="flex items-center gap-2 flex-wrap flex-1">
          <FilterChip
            ariaLabel="Severity"
            value={severityFilter}
            onChange={setSeverityFilter}
            options={[
              { value: 'ALL', label: 'All Severities' },
              { value: 'CRITICAL', label: 'Critical' },
              { value: 'HIGH', label: 'High' },
              { value: 'MEDIUM', label: 'Medium' },
              { value: 'LOW', label: 'Low' },
            ]}
          />
          <FilterChip ariaLabel="Review class" value={reviewFilter} onChange={setReviewFilter} options={[
            { value: 'ALL', label: 'Quality Issues' }, { value: 'INCOMPLETE', label: 'Incomplete Rows' },
            { value: 'CHRONOLOGY', label: 'Chronology Violations' }, { value: 'OUTLIERS', label: 'Outliers Only' },
          ]} />
          <FilterChip ariaLabel="File" value={fileFilter} onChange={setFileFilter} options={[
            { value: 'ALL', label: 'All Files' }, ...distinctFiles.map((value) => ({ value, label: value })),
          ]} />
          <FilterChip ariaLabel="Service" value={serviceFilter} onChange={setServiceFilter} options={[
            { value: 'ALL', label: 'All Services' }, ...distinctServices.map((value) => ({ value, label: value })),
          ]} />
          <FilterChip ariaLabel="Movement" value={movementFilter} onChange={setMovementFilter} options={[
            { value: 'ALL', label: 'All Movements' }, { value: 'ARRIVAL', label: 'Arrival / Inward' }, { value: 'SAILING', label: 'Sailing / Outward' }, { value: 'SHIFTING', label: 'Shifting' },
          ]} />

          <FilterChip
            ariaLabel="Status"
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: 'ALL', label: 'All Statuses' },
              { value: 'OPEN', label: 'Open' },
              { value: 'RESOLVED', label: 'Resolved' },
              { value: 'QUARANTINED', label: 'Quarantined' },
            ]}
          />

          <FilterChip
            ariaLabel="Rule"
            value={ruleFilter}
            onChange={setRuleFilter}
            options={[
              { value: 'ALL', label: 'All Rules' },
              ...distinctRules.map((r) => ({ value: r, label: r })),
            ]}
          />

          {hasActiveFilters && (
            <button
              onClick={() => {
                setSeverityFilter('ALL')
                setStatusFilter('ALL')
                setRuleFilter('ALL')
                setFileFilter('ALL')
                setServiceFilter('ALL')
                setMovementFilter('ALL')
              }}
              className="text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] underline text-xs cursor-pointer ml-1"
            >
              Reset Filters
            </button>
          )}
        </div>

        {/* Search Input */}
        <div className="relative w-72">
          <input
            type="text"
            placeholder="Search VCN, rule, description…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full text-xs bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-md px-3 py-1.5 pl-8 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          />
          <Search size={14} className="absolute left-2.5 top-2.5 text-[var(--color-text-tertiary)]" aria-hidden="true" />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2 top-1.5 flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text-primary)] cursor-pointer"
              aria-label="Clear search"
            >
              <X size={13} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {selectedIssueIds.length > 0 && reviewFilter !== 'OUTLIERS' && (
        <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-2.5 flex items-center gap-3 text-xs">
          <span className="font-semibold">{selectedIssueIds.length} selected</span>
          <input value={excludeReason} onChange={(event) => setExcludeReason(event.target.value)} placeholder="Reason for governed exclusion (required)" className="min-w-72 flex-1 max-w-xl rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5" />
          <button disabled={!excludeReason.trim() || excluding} onClick={excludeSelected} className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 font-semibold text-red-800 disabled:opacity-50">
            <Ban size={13} aria-hidden="true" /> {excluding ? 'Rebuilding…' : 'Exclude from active analysis'}
          </button>
        </div>
      )}

      {/* Issues Data Table */}
      <div className="w-full bg-[var(--color-surface)]">
        {loading ? (
          <LoadingState label="Loading Data Quality issues from governance engine…" />
        ) : error ? (
          <ErrorState
            title="Error Loading Quality Issues"
            description={error}
            onRetry={fetchQualityData}
          />
        ) : filteredIssues.length === 0 ? (
          <EmptyState
            title="No matching issues"
            description="No data quality issues match the selected criteria."
          />
        ) : (
          <table className="w-full table-fixed border-collapse text-left text-xs" aria-label="Data Quality Issues Table">
            <colgroup>
              <col className="w-[3%]" />
              <col className="w-[8%]" />
              <col className="w-[7%]" />
              <col className="w-[23%]" />
              <col className="w-[11%]" />
              <col className="w-[22%]" />
              <col className="w-[9%]" />
              <col className="w-[9%]" />
              <col className="w-[8%]" />
            </colgroup>
            <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] sticky top-0 z-10 select-none">
              <tr>
                <th className="px-2 py-2.5 border-b border-[var(--color-border)]"><input aria-label="Select all filtered quality issues" type="checkbox" checked={filteredIssues.length > 0 && filteredIssues.filter((issue) => issue.issue_class !== 'OUTLIER').every((issue) => selectedIssueIds.includes(issue.id))} onChange={(event) => setSelectedIssueIds(event.target.checked ? filteredIssues.filter((issue) => issue.issue_class !== 'OUTLIER').map((issue) => issue.id) : [])} /></th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Rule ID</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Severity</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Issue</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Affected Record</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Source / Original Value</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Disposition</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)]">Workflow State</th>
                <th className="px-2 py-2.5 font-semibold border-b border-[var(--color-border)] text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
              {filteredIssues.map((iss) => {
                const isResolved = iss.issue_status === 'RESOLVED'

                return (
                  <tr key={iss.id} className="hover:bg-[var(--color-surface-muted)] transition-colors">
                    <td className="px-2 py-2 align-top"><input aria-label={`Select ${iss.rule_id} issue`} disabled={iss.issue_class === 'OUTLIER' || isResolved} type="checkbox" checked={selectedIssueIds.includes(iss.id)} onChange={() => toggleSelected(iss.id)} /></td>
                    {/* Rule ID */}
                    <td className="break-words px-2 py-2 align-top font-mono text-[10px] font-semibold text-[var(--color-text-primary)]">
                      {iss.rule_id}
                    </td>

                    {/* Severity Badge */}
                    <td className="px-2 py-2 align-top">
                      <StatusBadge status={iss.severity || 'MEDIUM'} />
                    </td>

                    {/* Human-readable issue */}
                    <td className="break-words px-2 py-2 align-top text-[11px] leading-4 text-[var(--color-text-primary)]">
                      <div className="font-medium">{issueDescription(iss)}</div>
                      <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)]">
                        {iss.scope || 'VALIDITY'}
                        {iss.rule_name ? ` · ${iss.rule_name}` : ''}
                      </div>
                      {iss.remediation_guidance && (
                        <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)]">
                          Guidance: {iss.remediation_guidance}
                        </div>
                      )}
                    </td>

                    {/* Affected Record */}
                    <td className="break-words px-2 py-2 align-top">
                      {iss.vcn ? (
                        <div>
                          <Link
                            href={`/vessel-journey?vcn=${iss.vcn}`}
                            className="font-mono font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] hover:underline"
                            title="Drill into Vessel Journey"
                          >
                            {iss.vcn}
                          </Link>
                          <div className="mt-0.5 break-words text-[10px] text-[var(--color-text-tertiary)]">
                            {iss.vessel_name || '—'}
                          </div>
                        </div>
                      ) : (
                        <span className="text-[var(--color-text-tertiary)] italic">Global / Unattached</span>
                      )}
                    </td>

                    <td className="break-words px-2 py-2 align-top">
                      <div className="font-medium text-[var(--color-text-primary)]">{iss.source_file || 'Lineage unavailable'}</div>
                      {iss.source_sheet && <div className="mt-0.5 break-words font-mono text-[10px] text-[var(--color-text-tertiary)]">{iss.source_sheet} · row {iss.source_row ?? '—'} · {iss.source_field || 'record'}</div>}
                      <div className="mt-0.5 break-all font-mono text-[10px] text-[var(--color-text-tertiary)]" title={iss.record_reference}>{iss.record_reference}</div>
                      {iss.original_values && <div className="mt-1 break-all font-mono text-[10px] leading-4 text-[var(--color-text-tertiary)]" title={JSON.stringify(iss.original_values)}>{JSON.stringify(iss.original_values)}</div>}
                    </td>

                    {/* Disposition */}
                    <td className="px-2 py-2 align-top">
                      <StatusBadge
                        label={iss.disposition || 'FLAGGED'}
                        tone={iss.disposition === 'QUARANTINED' ? 'critical' : 'neutral'}
                      />
                    </td>

                    {/* Workflow State */}
                    <td className="px-2 py-2 align-top">
                      <StatusBadge
                        status={iss.issue_status}
                        tone={isResolved ? 'good' : statusToTone(iss.issue_status)}
                      />
                    </td>

                    {/* Action */}
                    <td className="px-2 py-2 align-top text-center">
                      <div className="flex flex-col items-stretch justify-center gap-1.5">
                        {iss.vcn && (
                          <Link
                            href={`/vessel-journey?vcn=${iss.vcn}`}
                            className="px-2 py-1 bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-[10px] font-semibold transition-colors"
                          >
                            Journey →
                          </Link>
                        )}
                        {!isResolved && (
                          <button
                            onClick={() => {
                              setResolveTarget(iss)
                              setResolutionNotes('')
                            }}
                            className="px-2 py-1 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-[10px] font-semibold transition-colors cursor-pointer"
                          >
                            Resolve
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Resolution Dialog Modal */}
      {resolveTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-[var(--color-surface)] rounded-lg shadow-xl max-w-md w-full border border-[var(--color-border)] overflow-hidden text-xs">
            <div className="border-b border-[var(--color-border)] px-5 py-3.5 flex items-center justify-between">
              <div className="font-semibold text-[var(--color-text-primary)]">
                Resolve Data Quality Issue: {resolveTarget.rule_id}
              </div>
              <button
                onClick={() => setResolveTarget(null)}
                className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-base font-bold cursor-pointer"
                aria-label="Close"
              >
                <X size={15} aria-hidden="true" />
              </button>
            </div>

            <form onSubmit={handleResolveIssue} className="p-5 space-y-4">
              <div className="bg-[var(--color-surface-muted)] p-3 rounded-md border border-[var(--color-border)] space-y-1 text-[var(--color-text-secondary)]">
                <div>
                  Record Key: <strong className="text-[var(--color-text-primary)]">{resolveTarget.vcn || resolveTarget.record_reference}</strong>
                </div>
                <div>
                  Rule Expression: <strong className="text-[var(--color-text-primary)]">{resolveTarget.rule_name || resolveTarget.rule_id}</strong>
                </div>
                <div>
                  Severity: <strong className="text-[var(--color-text-primary)]">{resolveTarget.severity}</strong>
                </div>
              </div>

              <div>
                <label className="block text-[var(--color-text-primary)] font-semibold mb-1">
                  Resolution Decision Notes:
                </label>
                <textarea
                  rows={3}
                  required
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="State reason for resolution (e.g. verified by terminal steward, manual timestamp envelope confirmed)..."
                  className="w-full border border-[var(--color-border)] rounded-md p-2 text-xs text-[var(--color-text-primary)] bg-[var(--color-surface)] focus:ring-2 focus:ring-[var(--color-accent)] focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border)]">
                <button
                  type="button"
                  onClick={() => setResolveTarget(null)}
                  className="px-3 py-1.5 border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-md hover:bg-[var(--color-surface-muted)] cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resolving}
                  className="px-4 py-1.5 bg-[var(--color-accent)] text-white font-semibold rounded-md hover:bg-[var(--color-accent-hover)] disabled:opacity-50 cursor-pointer"
                >
                  {resolving ? 'Submitting…' : 'Confirm Resolution'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default function DataQualityPage() {
  return (
    <React.Suspense
      fallback={
        <div className="p-8">
          <LoadingState label="Loading Data Quality Dashboard..." />
        </div>
      }
    >
      <DataQualityContent />
    </React.Suspense>
  )
}
