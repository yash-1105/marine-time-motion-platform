'use client'

import React, { useState, useEffect, useMemo, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth-context'

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
}

function DataQualityContent() {
  const { token } = useAuth()
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
        fetch(`${API}/api/v1/quality/issues`, { headers }),
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
  }, [headers])

  useEffect(() => {
    fetchQualityData()
  }, [fetchQualityData])

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
  }, [issues, severityFilter, statusFilter, ruleFilter, searchTerm])

  const distinctRules = useMemo(() => {
    const rules = new Set(issues.map((i) => i.rule_id))
    return Array.from(rules).sort()
  }, [issues])

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-100 text-slate-900">
      {/* 1. Top Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-3.5 flex-shrink-0 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-1.5">
              <span>🛡</span> Data Quality Governance &amp; Issue Resolution
            </h1>
            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 border border-slate-300 text-slate-700">
              {filteredIssues.length} issues
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Operational quality rules, chronology sequence assertions, quarantine enforcement, and steward remediation.
          </p>
        </div>

        <button
          onClick={fetchQualityData}
          className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-2xs"
        >
          <span>↺</span> Refresh Status
        </button>
      </div>

      {/* 2. Real KPI Summary Stat Cards */}
      {summary && (
        <div className="bg-slate-50 border-b border-slate-200 px-6 py-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 flex-shrink-0">
          <div className="bg-white p-2.5 rounded border border-slate-200 shadow-2xs">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Total Issues</div>
            <div className="text-lg font-bold font-mono text-slate-900 mt-0.5">{summary.total_issues}</div>
            <div className="text-[10px] text-slate-500">{summary.open_issues} active</div>
          </div>

          <div className="bg-white p-2.5 rounded border border-red-200 shadow-2xs bg-red-50/20">
            <div className="text-[10px] uppercase tracking-wider text-red-700 font-bold">Critical / Quarantined</div>
            <div className="text-lg font-bold font-mono text-red-700 mt-0.5">{summary.critical_issues}</div>
            <div className="text-[10px] text-red-600 font-medium">Excluded from KPIs</div>
          </div>

          <div className="bg-white p-2.5 rounded border border-amber-200 shadow-2xs bg-amber-50/20">
            <div className="text-[10px] uppercase tracking-wider text-amber-700 font-bold">High Severity</div>
            <div className="text-lg font-bold font-mono text-amber-700 mt-0.5">{summary.high_issues}</div>
            <div className="text-[10px] text-amber-600">Requires review</div>
          </div>

          <div className="bg-white p-2.5 rounded border border-slate-200 shadow-2xs">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Quarantined Calls</div>
            <div className="text-lg font-bold font-mono text-slate-800 mt-0.5">{summary.quarantined_calls_count}</div>
            <div className="text-[10px] text-slate-500">of {summary.total_active_calls} active calls</div>
          </div>

          <div className="bg-white p-2.5 rounded border border-emerald-200 shadow-2xs bg-emerald-50/20">
            <div className="text-[10px] uppercase tracking-wider text-emerald-700 font-bold">Clean Calls</div>
            <div className="text-lg font-bold font-mono text-emerald-700 mt-0.5">{summary.clean_calls_count}</div>
            <div className="text-[10px] text-emerald-600">Zero DQ issues</div>
          </div>

          <div className="bg-white p-2.5 rounded border border-slate-200 shadow-2xs">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Cleanliness Score</div>
            <div className="text-lg font-bold font-mono text-cyan-800 mt-0.5">
              {summary.cleanliness_percentage.toFixed(1)}%
            </div>
            <div className="text-[10px] text-slate-500">Governed composite</div>
          </div>
        </div>
      )}

      {/* 3. Filter and Search Bar */}
      <div className="bg-white border-b border-slate-200 px-6 py-2.5 flex items-center justify-between gap-3 flex-wrap flex-shrink-0 text-xs">
        <div className="flex items-center gap-2 flex-wrap flex-1">
          {/* Severity filter */}
          <div className="flex items-center gap-1">
            <span className="text-slate-500 font-semibold">Severity:</span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded px-2 py-1 text-xs focus:ring-1 focus:ring-cyan-600"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical [✕]</option>
              <option value="HIGH">High [⚠]</option>
              <option value="MEDIUM">Medium [!]</option>
              <option value="LOW">Low [i]</option>
            </select>
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-1">
            <span className="text-slate-500 font-semibold">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded px-2 py-1 text-xs focus:ring-1 focus:ring-cyan-600"
            >
              <option value="ALL">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="RESOLVED">Resolved</option>
              <option value="QUARANTINED">Quarantined</option>
            </select>
          </div>

          {/* Rule filter */}
          <div className="flex items-center gap-1">
            <span className="text-slate-500 font-semibold">Rule:</span>
            <select
              value={ruleFilter}
              onChange={(e) => setRuleFilter(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded px-2 py-1 text-xs focus:ring-1 focus:ring-cyan-600"
            >
              <option value="ALL">All Rules</option>
              {distinctRules.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters */}
          {(severityFilter !== 'ALL' || statusFilter !== 'ALL' || ruleFilter !== 'ALL') && (
            <button
              onClick={() => {
                setSeverityFilter('ALL')
                setStatusFilter('ALL')
                setRuleFilter('ALL')
              }}
              className="text-cyan-700 hover:text-cyan-900 underline text-xs cursor-pointer ml-1"
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
            className="w-full text-xs bg-slate-50 border border-slate-300 rounded px-3 py-1.5 pl-8 focus:outline-none focus:ring-1 focus:ring-cyan-600"
          />
          <span className="absolute left-2.5 top-1.5 text-slate-400 text-xs">🔍</span>
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-1.5 text-slate-400 hover:text-slate-600 text-xs"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 4. Issues Data Table */}
      <div className="flex-1 overflow-auto bg-white">
        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-sm gap-2">
            <span className="inline-block animate-spin text-xl">⚙</span>
            <span>Loading Data Quality issues from governance engine…</span>
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="text-sm font-semibold text-red-600 mb-2">Error Loading Quality Issues</p>
            <p className="text-xs text-slate-600 mb-4">{error}</p>
            <button
              onClick={fetchQualityData}
              className="px-3 py-1.5 bg-slate-800 text-white rounded text-xs hover:bg-slate-700"
            >
              Retry
            </button>
          </div>
        ) : filteredIssues.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-500 text-sm">
            <span>No data quality issues match the selected criteria.</span>
          </div>
        ) : (
          <table className="w-full border-collapse text-left text-xs" aria-label="Data Quality Issues Table">
            <thead className="bg-slate-900 text-slate-200 sticky top-0 z-10 select-none">
              <tr>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 whitespace-nowrap">Rule ID</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 whitespace-nowrap">Severity</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 whitespace-nowrap">Scope / Domain</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700">Affected Record (VCN)</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700">Record Reference</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 whitespace-nowrap">Disposition</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700">Rule Expression &amp; Guidance</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 whitespace-nowrap">Workflow State</th>
                <th className="px-3 py-2.5 font-semibold border-b border-slate-700 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {filteredIssues.map((iss, idx) => {
                const isCritical = iss.severity === 'CRITICAL'
                const isHigh = iss.severity === 'HIGH'
                const isResolved = iss.issue_status === 'RESOLVED'

                return (
                  <tr
                    key={iss.id}
                    className={`hover:bg-slate-50 transition-colors ${
                      idx % 2 === 1 ? 'bg-slate-50/50' : 'bg-white'
                    } ${isCritical && !isResolved ? 'bg-red-50/40' : ''}`}
                  >
                    {/* Rule ID */}
                    <td className="px-3 py-2 font-mono font-bold text-slate-900 whitespace-nowrap">
                      {iss.rule_id}
                    </td>

                    {/* Severity Badge */}
                    <td className="px-3 py-2 whitespace-nowrap">
                      {isCritical ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-200">
                          <span>✕</span> CRITICAL
                        </span>
                      ) : isHigh ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                          <span>⚠</span> HIGH
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                          <span>!</span> {iss.severity || 'MEDIUM'}
                        </span>
                      )}
                    </td>

                    {/* Scope */}
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-600 whitespace-nowrap">
                      {iss.scope || 'VALIDITY'}
                    </td>

                    {/* Affected Record */}
                    <td className="px-3 py-2">
                      {iss.vcn ? (
                        <div>
                          <Link
                            href={`/vessel-journey?vcn=${iss.vcn}`}
                            className="font-mono font-bold text-cyan-700 hover:text-cyan-900 hover:underline"
                            title="Drill into Vessel Journey"
                          >
                            {iss.vcn}
                          </Link>
                          <div className="text-[10px] text-slate-500 truncate max-w-[160px]">
                            {iss.vessel_name || '—'}
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">Global / Unattached</span>
                      )}
                    </td>

                    {/* Record Reference */}
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-500 truncate max-w-[140px]" title={iss.record_reference}>
                      {iss.record_reference}
                    </td>

                    {/* Disposition */}
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          iss.disposition === 'QUARANTINED'
                            ? 'bg-red-700 text-white'
                            : 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        {iss.disposition || 'FLAGGED'}
                      </span>
                    </td>

                    {/* Rule Expression & Guidance */}
                    <td className="px-3 py-2 max-w-xs">
                      <div className="font-medium text-slate-800 text-[11px] truncate" title={iss.rule_name || ''}>
                        {iss.rule_name || iss.rule_id}
                      </div>
                      {iss.remediation_guidance && (
                        <div className="text-[10px] text-slate-500 truncate" title={iss.remediation_guidance}>
                          Guidance: {iss.remediation_guidance}
                        </div>
                      )}
                    </td>

                    {/* Workflow State */}
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          isResolved
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {iss.issue_status}
                      </span>
                    </td>

                    {/* Action */}
                    <td className="px-3 py-2 text-center whitespace-nowrap">
                      <div className="flex items-center justify-center gap-1.5">
                        {iss.vcn && (
                          <Link
                            href={`/vessel-journey?vcn=${iss.vcn}`}
                            className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-[10px] font-semibold transition-colors"
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
                            className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[10px] font-semibold transition-colors cursor-pointer"
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

      {/* 5. Resolution Dialog Modal */}
      {resolveTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-2xs p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-lg shadow-2xl max-w-md w-full border border-slate-200 overflow-hidden text-xs">
            <div className="bg-slate-900 text-white px-5 py-3.5 flex items-center justify-between">
              <div className="font-bold">
                Resolve Data Quality Issue: {resolveTarget.rule_id}
              </div>
              <button
                onClick={() => setResolveTarget(null)}
                className="text-slate-400 hover:text-white text-base font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleResolveIssue} className="p-5 space-y-4">
              <div className="bg-slate-50 p-3 rounded border border-slate-200 space-y-1">
                <div>Record Key: <strong>{resolveTarget.vcn || resolveTarget.record_reference}</strong></div>
                <div>Rule Expression: <strong>{resolveTarget.rule_name || resolveTarget.rule_id}</strong></div>
                <div>Severity: <strong>{resolveTarget.severity}</strong></div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">
                  Resolution Decision Notes:
                </label>
                <textarea
                  rows={3}
                  required
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="State reason for resolution (e.g. verified by terminal steward, manual timestamp envelope confirmed)..."
                  className="w-full border border-slate-300 rounded p-2 text-xs focus:ring-1 focus:ring-cyan-600 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setResolveTarget(null)}
                  className="px-3 py-1.5 border border-slate-300 text-slate-700 rounded hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resolving}
                  className="px-4 py-1.5 bg-emerald-600 text-white font-semibold rounded hover:bg-emerald-700 disabled:opacity-50 cursor-pointer"
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
    <React.Suspense fallback={<div className="p-8 text-xs text-slate-500">Loading Data Quality Dashboard...</div>}>
      <DataQualityContent />
    </React.Suspense>
  )
}
