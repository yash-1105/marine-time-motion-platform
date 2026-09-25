'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'
import { X } from 'lucide-react'
import {
  PageHeader,
  SectionHeader,
  Card,
  KpiCard,
  StatusBadge,
  EmptyState,
  LoadingState,
  ErrorState,
} from '@/components/ui'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Interfaces ──────────────────────────────────────────────────────────────

interface DelayItem {
  id: string
  source_delay_id?: string
  vessel_call_id: string
  vcn: string
  vessel_name?: string
  movement_stage: string
  total_duration_hours: number
  is_early_service: boolean
  scheduled_time?: string
  served_time?: string
  delay_hours?: number
  recalculated_delay_hours?: number
  delay_reason?: string
  source_category?: string
  canonical_category?: string
  cause_status: string
  confidence?: string
  resolution_status: string
  has_reconciliation_mismatch: boolean
  reconciliation_notes?: string
  requires_reason_review: boolean
  allocated_duration_hours: number
  unallocated_duration_hours: number
  allocations_count: number
}

interface DelayAllocation {
  id: string
  cause: string
  canonical_category?: string
  reason?: string
  duration_hours: number
  is_primary: boolean
  cause_status: string
  confidence?: number
  inference_evidence?: Record<string, unknown> | null
  human_review_state: string
}

interface DelayDetail extends DelayItem {
  allocations: DelayAllocation[]
}

interface ParetoCategory {
  category: string
  count: number
  total_hours: number
  cumulative_percentage: number
}

interface DelaysSummary {
  total_delays: number
  total_delay_hours: number
  confirmed_count: number
  inferred_count: number
  total_allocated_hours: number
  total_unallocated_hours: number
  reconciliation_mismatches_count: number
  review_required_count: number
  pareto_categories: ParetoCategory[]
  stage_breakdown: Array<{ stage: string; count: number; total_hours: number }>
}

interface ServiceTiming { service_request_id: string; vcn?: string; vessel_name?: string; movement?: string; leg: string; service_type: string; scheduling_gap_hours?: number | null; execution_delay_hours?: number | null; service_duration_hours?: number | null; execution_delay_status: string; data_quality_status: string; service_duration_reason?: string }

interface ServiceDelayMetric {
  key: string
  label: string
  status: 'AVAILABLE' | 'UNAVAILABLE'
  average_hours?: number | null
  observation_count: number
  delayed_count?: number | null
  on_time_count?: number | null
  early_count?: number | null
  formula: string
  unavailable_reason?: string | null
}

interface DelayFrequencyMetric {
  leg: string
  label: string
  status: 'AVAILABLE' | 'UNAVAILABLE'
  eligible_event_count: number
  delayed_event_count: number
  delay_frequency_percent?: number | null
  classification: 'ACCEPTABLE' | 'WATCH' | 'CRITICAL' | 'UNAVAILABLE'
  band: 'GREEN' | 'ORANGE' | 'RED' | 'GRAY'
  unavailable_reason?: string | null
}

interface ServiceDurationRange {
  service_type: string
  status: 'AVAILABLE' | 'UNAVAILABLE'
  min_hours?: number | null
  max_hours?: number | null
  observation_count: number
  formula?: string
  unavailable_reason?: string | null
}

interface BottleneckItem {
  rank: number
  stage_or_resource: string
  bottleneck_type: 'RESOURCE_BOTTLENECK' | 'PROCESS_BOTTLENECK'
  overall_bottleneck_score: number
  mean_hours: number
  median_hours: number
  p90_hours: number
  cv: number
  tail_risk_ratio: number
  turnaround_contribution: number
  repeated_target_breach_rate: number
  business_criticality_score: number
  duration_score: number
  frequency_score: number
  variability_score: number
  tail_risk_score: number
  turnaround_contribution_score: number
  target_breach_score: number
}

interface OutlierItem {
  id: string
  vessel_call_id: string
  vcn: string
  vessel_name?: string
  outlier_type: string
  rule_id?: string
  metric_name: string
  observed_value: number | null
  benchmark_or_p90?: number | null
  divergence?: number | null
  issue_text?: string
  threshold_label?: string
  reason?: string
  movement_leg?: string
  source_record_ids?: string[]
  is_excluded_from_kpi: boolean
  exclusion_rationale?: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  evidence?: Record<string, unknown> | null
  detected_at?: string
}

interface CriticalityItem {
  stage_name: string
  definition_id?: string
  duration_score: number
  variability_score: number
  tail_risk_score: number
  overall_score: number
  band: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
  observations: number
  metrics?: {
    mean_hours: number
    median_hours: number
    p90_hours: number
    cv: number
    tail_risk_ratio: number
  }
}

interface OperationalAlertItem {
  id: string
  rule_code: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  title: string
  description?: string
  vessel_call_id?: string
  vcn?: string
  status: 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED'
  acknowledged_at?: string
  acknowledged_by?: string
  resolved_at?: string
  resolved_by?: string
  resolution_notes?: string
  evidence?: Record<string, unknown> | null
  created_at?: string
  actions_count: number
}

interface ActionItemRecord {
  id: string
  title: string
  description?: string
  assigned_to?: string
  due_date?: string
  status: 'OPEN' | 'IN_PROGRESS' | 'COMPLETED'
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'
  created_by?: string
  created_at?: string
}

type TabType = 'delays' | 'bottlenecks' | 'outliers' | 'criticality' | 'alerts'

// Criticality band -> status tone (bands don't map onto statusToTone's vocabulary directly)
function bandTone(band: string): 'good' | 'warning' | 'critical' | 'neutral' {
  if (band === 'CRITICAL') return 'critical'
  if (band === 'HIGH') return 'warning'
  if (band === 'MODERATE') return 'neutral'
  return 'good'
}

function severityTone(severity: string): 'good' | 'warning' | 'critical' | 'neutral' {
  if (severity === 'CRITICAL') return 'critical'
  if (severity === 'HIGH') return 'warning'
  if (severity === 'MEDIUM') return 'neutral'
  return 'good'
}

function compactDuration(hours: number | null | undefined, preserveNegative = false): string {
  if (hours == null) return 'Unavailable'
  const totalMinutes = Math.round(Math.abs(hours) * 60)
  const hourPart = Math.floor(totalMinutes / 60)
  const minutePart = totalMinutes % 60
  const value = hourPart > 0 ? `${hourPart}h ${minutePart}m` : `${minutePart}m`
  if (!preserveNegative) return value
  return `${hours < 0 ? '−' : ''}${value}`
}

export default function DelaysAndBottlenecksPage() {
  const { token, isLoading: authLoading } = useAuth()
  const [activeTab, setActiveTab] = useState<TabType>('delays')

  // Summary & Delays state
  const [summary, setSummary] = useState<DelaysSummary | null>(null)
  const [delays, setDelays] = useState<DelayItem[]>([])
  const [delaysTotal, setDelaysTotal] = useState(0)
  const [delaysLoading, setDelaysLoading] = useState(false)
  const [delaysError, setDelaysError] = useState<string | null>(null)
  const [stageFilter, setStageFilter] = useState('')
  const [legFilter, setLegFilter] = useState('ALL')
  const [serviceTimings, setServiceTimings] = useState<ServiceTiming[]>([])
  const [serviceDelayMetrics, setServiceDelayMetrics] = useState<ServiceDelayMetric[]>([])
  const [delayFrequencyMetrics, setDelayFrequencyMetrics] = useState<DelayFrequencyMetric[]>([])
  const [serviceDurationRanges, setServiceDurationRanges] = useState<ServiceDurationRange[]>([])
  const [categoryFilter, setCategoryFilter] = useState('')
  const [causeStatusFilter, setCauseStatusFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [reviewFilter, setReviewFilter] = useState<boolean | null>(null)
  const [selectedDelay, setSelectedDelay] = useState<DelayDetail | null>(null)

  // Bottlenecks state
  const [bottlenecks, setBottlenecks] = useState<BottleneckItem[]>([])
  const [bnTypeFilter, setBnTypeFilter] = useState('')
  const [bnLoading, setBnLoading] = useState(false)

  // Outliers state
  const [outliers, setOutliers] = useState<OutlierItem[]>([])
  const [outliersLoading, setOutliersLoading] = useState(false)
  const [outlierModal, setOutlierModal] = useState<OutlierItem | null>(null)
  const [exclusionRationale, setExclusionRationale] = useState('')

  // Criticality state
  const [criticalities, setCriticalities] = useState<CriticalityItem[]>([])
  const [critLoading, setCritLoading] = useState(false)

  // Alerts state
  const [alerts, setAlerts] = useState<OperationalAlertItem[]>([])
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [actionItems, setActionItems] = useState<ActionItemRecord[]>([])
  const [resolvingAlert, setResolvingAlert] = useState<OperationalAlertItem | null>(null)
  const [resolveNotes, setResolveNotes] = useState('')
  const [newActionModal, setNewActionModal] = useState<OperationalAlertItem | null>(null)
  const [newActionTitle, setNewActionTitle] = useState('')
  const [newActionDesc, setNewActionDesc] = useState('')
  const [newActionAssignee, setNewActionAssignee] = useState('')
  const [newActionPriority, setNewActionPriority] = useState('HIGH')

  // Review DQ-007 state
  const [reviewingDelay, setReviewingDelay] = useState<DelayItem | null>(null)
  const [reviewCategory, setReviewCategory] = useState('Pilot')
  const [reviewReason, setReviewReason] = useState('')

  // Check URL query param for tab selection
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      const tabParam = params.get('tab')
      if (tabParam && ['delays', 'bottlenecks', 'outliers', 'criticality', 'alerts'].includes(tabParam)) {
        setActiveTab(tabParam as TabType)
      }
    }
  }, [])

  // 1. Fetch Summary
  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/delays/summary?leg=ALL`, {
        headers: { Authorization: `Bearer ${token || 'dev-token'}` },
      })
      if (res.ok) {
        const data = await res.json()
        setSummary(data)
        setDelaysError(null)
      } else {
        setDelaysError(`Failed to load delay summary: HTTP ${res.status}`)
      }
    } catch (e) {
      console.error('Failed to load delays summary', e)
      setDelaysError('Network error while loading delay summary')
    }
  }, [token])

  // 2. Fetch Delays List
  const fetchDelays = useCallback(async () => {
    setDelaysLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('leg', legFilter)
      if (stageFilter) params.append('stage', stageFilter)
      if (categoryFilter) params.append('category', categoryFilter)
      if (causeStatusFilter) params.append('cause_status', causeStatusFilter)
      if (searchQuery) params.append('search', searchQuery)
      if (reviewFilter !== null) params.append('requires_review', String(reviewFilter))
      params.append('limit', '100')

      const res = await fetch(`${API}/api/v1/delays?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token || 'dev-token'}` },
      })
      if (res.ok) {
        const data = await res.json()
        setDelays(data.items || [])
        setDelaysTotal(data.total || 0)
        setDelaysError(null)
      } else {
        setDelaysError(`Failed to load delays: HTTP ${res.status}`)
      }
    } catch (e) {
      console.error('Failed to load delays', e)
      setDelaysError('Network error while loading delays')
    } finally {
      setDelaysLoading(false)
    }
  }, [token, legFilter, stageFilter, categoryFilter, causeStatusFilter, searchQuery, reviewFilter])

  const fetchServiceTimings = useCallback(async () => {
    const res = await fetch(`${API}/api/v1/delays/service-timings?leg=${legFilter}`, { headers: { Authorization: `Bearer ${token || 'dev-token'}` } })
    if (res.ok) {
      const data = await res.json()
      setServiceTimings(data.items || [])
      setServiceDelayMetrics(data.delay_overview || [])
      setDelayFrequencyMetrics(data.delay_frequency_by_leg || [])
      setServiceDurationRanges(data.duration_ranges || [])
    }
  }, [token, legFilter])

  // 3. Fetch Bottlenecks
  const fetchBottlenecks = useCallback(async () => {
    if (!token) return
    setBnLoading(true)
    try {
      const res = await fetch(`${API}/api/v1/bottlenecks`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setBottlenecks(data || [])
      }
    } catch (e) {
      console.error('Failed to load bottlenecks', e)
    } finally {
      setBnLoading(false)
    }
  }, [token])

  // 4. Fetch Outliers
  const fetchOutliers = useCallback(async () => {
    if (!token) return
    setOutliersLoading(true)
    try {
      const res = await fetch(`${API}/api/v1/outliers`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setOutliers(data || [])
      }
    } catch (e) {
      console.error('Failed to load outliers', e)
    } finally {
      setOutliersLoading(false)
    }
  }, [token])

  // 5. Fetch Criticality
  const fetchCriticality = useCallback(async () => {
    if (!token) return
    setCritLoading(true)
    try {
      const res = await fetch(`${API}/api/v1/criticality`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setCriticalities(data || [])
      }
    } catch (e) {
      console.error('Failed to load criticality', e)
    } finally {
      setCritLoading(false)
    }
  }, [token])

  // 6. Fetch Alerts & Actions
  const fetchAlertsAndActions = useCallback(async () => {
    if (!token) return
    setAlertsLoading(true)
    try {
      // Evaluate rules first to make sure new operational anomalies are flagged
      await fetch(`${API}/api/v1/alerts/evaluate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })

      const resAlerts = await fetch(`${API}/api/v1/alerts`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resAlerts.ok) {
        const data = await resAlerts.json()
        setAlerts(data || [])
      }

      const resActions = await fetch(`${API}/api/v1/alerts/actions`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resActions.ok) {
        const data = await resActions.json()
        setActionItems(data || [])
      }
    } catch (e) {
      console.error('Failed to load alerts', e)
    } finally {
      setAlertsLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (authLoading) return
    fetchSummary()
    fetchDelays()
    fetchServiceTimings()
  }, [authLoading, fetchSummary, fetchDelays, fetchServiceTimings])

  useEffect(() => {
    if (authLoading) return
    if (activeTab === 'bottlenecks') fetchBottlenecks()
    if (activeTab === 'outliers') fetchOutliers()
    if (activeTab === 'criticality') fetchCriticality()
    if (activeTab === 'alerts') fetchAlertsAndActions()
  }, [authLoading, activeTab, fetchBottlenecks, fetchOutliers, fetchCriticality, fetchAlertsAndActions])

  // Actions
  const handleOpenDetail = async (delayId: string) => {
    if (!token) return
    try {
      const res = await fetch(`${API}/api/v1/delays/${delayId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setSelectedDelay(data)
      }
    } catch (e) {
      console.error('Failed to load delay detail', e)
    }
  }

  const handleInferCause = async (delayId: string) => {
    if (!token) return
    try {
      const res = await fetch(`${API}/api/v1/delays/${delayId}/infer`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        await fetchDelays()
        await fetchSummary()
        if (selectedDelay && selectedDelay.id === delayId) {
          handleOpenDetail(delayId)
        }
      }
    } catch (e) {
      console.error('Failed to run inference', e)
    }
  }

  const handleReviewSubmit = async () => {
    if (!token || !reviewingDelay) return
    try {
      const res = await fetch(`${API}/api/v1/delays/${reviewingDelay.id}/review`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          canonical_category: reviewCategory,
          reason: reviewReason,
          decision: 'APPROVED',
          notes: 'Mandatory reason review approved by steward',
        }),
      })
      if (res.ok) {
        setReviewingDelay(null)
        setReviewReason('')
        await fetchDelays()
        await fetchSummary()
      }
    } catch (e) {
      console.error('Failed to review delay reason', e)
    }
  }

  const handleToggleExclusion = async () => {
    if (!token || !outlierModal) return
    try {
      const res = await fetch(`${API}/api/v1/outliers/${outlierModal.id}/exclusion`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          is_excluded: !outlierModal.is_excluded_from_kpi,
          rationale: exclusionRationale || 'Governance review of operational outlier',
        }),
      })
      if (res.ok) {
        setOutlierModal(null)
        setExclusionRationale('')
        await fetchOutliers()
      }
    } catch (e) {
      console.error('Failed to toggle outlier exclusion', e)
    }
  }

  const handleAcknowledgeAlert = async (alertId: string) => {
    if (!token) return
    try {
      const res = await fetch(`${API}/api/v1/alerts/${alertId}/acknowledge`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        await fetchAlertsAndActions()
      }
    } catch (e) {
      console.error('Failed to acknowledge alert', e)
    }
  }

  const handleResolveAlert = async () => {
    if (!token || !resolvingAlert) return
    try {
      const res = await fetch(`${API}/api/v1/alerts/${resolvingAlert.id}/resolve`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          resolution_notes: resolveNotes || 'Mitigation action confirmed by operations controller',
        }),
      })
      if (res.ok) {
        setResolvingAlert(null)
        setResolveNotes('')
        await fetchAlertsAndActions()
      }
    } catch (e) {
      console.error('Failed to resolve alert', e)
    }
  }

  const handleCreateAction = async () => {
    if (!token) return
    try {
      const res = await fetch(`${API}/api/v1/alerts/actions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: newActionTitle,
          description: newActionDesc,
          assigned_to: newActionAssignee,
          priority: newActionPriority,
          alert_id: newActionModal?.id,
          vessel_call_id: newActionModal?.vessel_call_id,
        }),
      })
      if (res.ok) {
        setNewActionModal(null)
        setNewActionTitle('')
        setNewActionDesc('')
        setNewActionAssignee('')
        await fetchAlertsAndActions()
      }
    } catch (e) {
      console.error('Failed to create action', e)
    }
  }

  const inputClass =
    'text-xs px-3 py-1.5 border border-[var(--color-border)] rounded-md bg-[var(--color-surface)] text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] placeholder:text-[var(--color-text-tertiary)]'

  const TABS: Array<{ id: TabType; label: string }> = [
    { id: 'delays', label: 'Delay Causes & Pareto' },
    { id: 'bottlenecks', label: 'Bottleneck Scoring' },
    { id: 'outliers', label: 'Outliers' },
    { id: 'criticality', label: 'Operational Criticality' },
    { id: 'alerts', label: 'Alerts & Actions' },
  ]

  return (
    <div className="flex flex-col min-h-full">
      <PageHeader title="Delays & Bottlenecks" />

      <div className="px-6 py-6 space-y-6">
        {/* KPI Row */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KpiCard label="Total Delays" value={summary ? summary.total_delays : '—'} context="41 fixture delays" />
          <KpiCard
            label="Delay Hours"
            value={summary ? summary.total_delay_hours : '—'}
            unit={summary ? 'h' : undefined}
            context="Sum of durations"
          />
          <KpiCard
            label="Confirmed / Inferred"
            value={summary ? `${summary.confirmed_count} / ${summary.inferred_count}` : '—'}
          />
          <KpiCard
            label="Unallocated Time"
            value={summary ? summary.total_unallocated_hours : '—'}
            unit={summary ? 'h' : undefined}
            context="Remainder explicit"
          />
          <KpiCard
            label="Reconciled Clean"
            value={
              summary ? `${summary.total_delays - summary.reconciliation_mismatches_count} / ${summary.total_delays}` : '—'
            }
            tone="good"
            context="Served − Sched ±0.02h"
          />
          <KpiCard
            label="DQ-007 Reviews"
            value={summary ? summary.review_required_count : '—'}
            tone={summary && summary.review_required_count > 0 ? 'critical' : 'good'}
            context="Requires reason"
          />
        </div>

        {delaysError && !summary && (
          <Card>
            <ErrorState
              title="Failed to load delay data"
              description={delaysError}
              onRetry={() => {
                fetchSummary()
                fetchDelays()
              }}
            />
          </Card>
        )}

        {/* Navigation Tabs */}
        <div className="flex border-b border-[var(--color-border)] gap-1 text-sm font-medium overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 border-b-2 whitespace-nowrap font-medium transition-colors cursor-pointer ${
                activeTab === tab.id
                  ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-semibold'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Tab 1: Delay Causes & Pareto ────────────────────────────────────── */}
        {activeTab === 'delays' && (
          <div className="space-y-6">
            {/* Pareto Distribution */}
            {summary && summary.pareto_categories.length > 0 && (
              <Card>
                <SectionHeader
                  title="Delay Cause Pareto Distribution"
                  description="Canonical delay category contribution ranked by total impact hours with cumulative share."
                />
                <div className="space-y-3">
                  {summary.pareto_categories.slice(0, 6).map((cat, idx) => (
                    <div key={cat.category} className="flex items-center gap-3">
                      <span className="w-6 text-xs font-semibold text-[var(--color-text-tertiary)] tabular-nums">
                        #{idx + 1}
                      </span>
                      <span className="w-40 shrink-0 text-sm font-medium text-[var(--color-text-primary)] truncate">
                        {cat.category}
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-[var(--color-accent)]"
                          style={{ width: `${Math.min(100, cat.cumulative_percentage)}%` }}
                        />
                      </div>
                      <span className="w-16 shrink-0 text-right text-sm font-semibold text-[var(--color-text-primary)] tabular-nums">
                        {cat.total_hours}h
                      </span>
                      <span className="w-24 shrink-0 text-right text-xs text-[var(--color-text-tertiary)] tabular-nums">
                        {cat.count} occ.
                      </span>
                      <span className="w-20 shrink-0 text-right text-xs text-[var(--color-text-tertiary)] tabular-nums">
                        {cat.cumulative_percentage}% cum.
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            <div className="space-y-3">
              <SectionHeader
                title="Service Delay Overview"
                description="Governed service timing metrics across the complete active dataset."
              />
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                {serviceDelayMetrics.map((metric) => {
                  const executionMetric = metric.delayed_count != null
                  return (
                    <Card key={metric.key} className="min-w-0 !p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-semibold text-[var(--color-text-secondary)]">{metric.label}</p>
                        <StatusBadge label={metric.status === 'AVAILABLE' ? 'Available' : 'Unavailable'} tone={metric.status === 'AVAILABLE' ? 'good' : 'neutral'} showGlyph={false} />
                      </div>
                      {metric.status === 'AVAILABLE' ? (
                        <>
                          <p className="mt-2 text-xl font-semibold tabular-nums text-[var(--color-text-primary)]">
                            {compactDuration(metric.average_hours, executionMetric)}
                          </p>
                          <p className="mt-1 text-[11px] text-[var(--color-text-tertiary)]">Average · {metric.observation_count} observations</p>
                          {executionMetric ? (
                            <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[10px] font-medium text-[var(--color-text-secondary)]">
                              <span><strong className="text-[var(--color-warning)]">{metric.delayed_count}</strong> late</span>
                              <span><strong className="text-[var(--color-text-primary)]">{metric.on_time_count}</strong> on time</span>
                              <span><strong className="text-[var(--color-good)]">{metric.early_count}</strong> early</span>
                            </div>
                          ) : (
                            <p className="mt-2 text-[10px] text-[var(--color-text-secondary)]">Governed wait duration</p>
                          )}
                        </>
                      ) : (
                        <p className="mt-3 text-[11px] leading-4 text-[var(--color-text-tertiary)]">{metric.unavailable_reason}</p>
                      )}
                      <p className="mt-2 text-[10px] text-[var(--color-text-tertiary)]">{metric.formula}</p>
                    </Card>
                  )
                })}
              </div>
              <div className="grid gap-2 sm:grid-cols-3">
                {delayFrequencyMetrics.map((metric) => (
                  <Card key={metric.leg} className="!p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold text-[var(--color-text-secondary)]">{metric.label}</p>
                        <p className="mt-1 text-[10px] text-[var(--color-text-tertiary)]">Delay Frequency</p>
                      </div>
                      {metric.status === 'AVAILABLE' ? (
                        <div className="text-right">
                          <p className="text-xl font-semibold tabular-nums text-[var(--color-text-primary)]">{metric.delay_frequency_percent}%</p>
                          <StatusBadge
                            label={metric.classification}
                            tone={metric.band === 'GREEN' ? 'good' : metric.band === 'ORANGE' ? 'warning' : 'critical'}
                            showGlyph={false}
                          />
                        </div>
                      ) : (
                        <StatusBadge label="Unavailable" tone="neutral" showGlyph={false} />
                      )}
                    </div>
                    <p className="mt-2 text-[10px] text-[var(--color-text-tertiary)]">
                      {metric.status === 'AVAILABLE'
                        ? `${metric.delayed_event_count} delayed / ${metric.eligible_event_count} eligible`
                        : metric.unavailable_reason}
                    </p>
                  </Card>
                ))}
              </div>
            </div>

            <Card>
              <SectionHeader
                title="Service Duration Range"
                description="Minimum and maximum observed duration from service-specific governed event pairs across the active dataset."
              />
              <div className="space-y-4">
                {serviceDurationRanges.map((range) => {
                  const availableMaxima = serviceDurationRanges.flatMap((item) => item.max_hours == null ? [] : [item.max_hours])
                  const scaleMax = Math.max(...availableMaxima, 1)
                  const minPosition = range.min_hours == null ? 0 : Math.max(0, Math.min(100, (range.min_hours / scaleMax) * 100))
                  const maxPosition = range.max_hours == null ? 0 : Math.max(0, Math.min(100, (range.max_hours / scaleMax) * 100))
                  return (
                    <div key={range.service_type} className="grid items-center gap-3 md:grid-cols-[150px_minmax(0,1fr)_100px]">
                      <div>
                        <p className="text-xs font-semibold text-[var(--color-text-primary)]">{range.service_type}</p>
                        <p className="text-[10px] text-[var(--color-text-tertiary)]">{range.observation_count} observations</p>
                        {range.formula && <p className="mt-0.5 text-[9px] text-[var(--color-text-tertiary)]">{range.formula}</p>}
                      </div>
                      {range.status === 'AVAILABLE' ? (
                        <div className="relative h-7" aria-label={`${range.service_type}: minimum ${compactDuration(range.min_hours)}, maximum ${compactDuration(range.max_hours)}`}>
                          <div className="absolute left-0 right-0 top-3 h-1 rounded-full bg-[var(--color-surface-muted)]" />
                          <div className="absolute top-3 h-1 rounded-full bg-[var(--color-accent)]" style={{ left: `${minPosition}%`, width: `${Math.max(maxPosition - minPosition, 0.5)}%` }} />
                          <span className="absolute top-1.5 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white bg-[var(--color-accent)] shadow-sm" style={{ left: `${minPosition}%` }} />
                          <span className="absolute top-1.5 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white bg-[var(--color-accent)] shadow-sm" style={{ left: `${maxPosition}%` }} />
                        </div>
                      ) : (
                        <div className="rounded-md bg-[var(--color-surface-muted)] px-3 py-2 text-[11px] text-[var(--color-text-tertiary)]">{range.unavailable_reason}</div>
                      )}
                      <div className="text-right text-[11px] tabular-nums text-[var(--color-text-secondary)]">
                        {range.status === 'AVAILABLE' ? <><span className="block">Min {compactDuration(range.min_hours)}</span><span className="block">Max {compactDuration(range.max_hours)}</span></> : 'Unavailable'}
                      </div>
                    </div>
                  )
                })}
                {serviceDurationRanges.length === 0 && <EmptyState title="No governed service duration definitions are available" />}
              </div>
            </Card>

            {/* Table-only filters */}
            <Card padded={false} className="p-3">
              <div className="mb-2 text-xs font-semibold text-[var(--color-text-primary)]">Table filters</div>
              <div className="flex flex-wrap items-center gap-2">
                <select value={legFilter} onChange={(e) => setLegFilter(e.target.value)} className={inputClass} aria-label="Operational delay leg">
                  <option value="ALL">All legs</option><option value="ARRIVAL_INWARD">Arrival / Inward</option><option value="SAILING_OUTWARD">Sailing / Outward</option><option value="SHIFTING">Shifting</option>
                </select>
                <input
                  type="text"
                  placeholder="Search VCN, reason, vessel..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className={`${inputClass} w-56`}
                />
                <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)} className={inputClass}>
                  <option value="">All Movement Stages</option>
                  <option value="Arrival">Arrival</option>
                  <option value="Sailing">Sailing</option>
                  <option value="Shifting">Shifting</option>
                </select>
                <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className={inputClass}>
                  <option value="">All Categories</option>
                  <option value="Weather">Weather</option>
                  <option value="Tug">Tug</option>
                  <option value="Pilot">Pilot</option>
                  <option value="Berth Non-Availability">Berth Non-Availability</option>
                  <option value="Terminal Readiness">Terminal Readiness</option>
                  <option value="Vessel-Side">Vessel-Side</option>
                  <option value="Port-Side">Port-Side</option>
                  <option value="Documentation">Documentation</option>
                </select>
                <select value={causeStatusFilter} onChange={(e) => setCauseStatusFilter(e.target.value)} className={inputClass}>
                  <option value="">All Cause Statuses</option>
                  <option value="Confirmed">Confirmed</option>
                  <option value="Inferred">Inferred</option>
                </select>
                <button
                  onClick={() => setReviewFilter(reviewFilter === true ? null : true)}
                  className={`text-xs px-2.5 py-1.5 rounded-md border cursor-pointer transition-colors ${
                    reviewFilter === true
                      ? 'bg-[var(--color-critical-bg)] border-[var(--color-critical-border)] text-[var(--color-critical)] font-semibold'
                      : 'bg-[var(--color-surface)] border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)]'
                  }`}
                >
                  Missing Reason Review (DQ-007)
                </button>
                <div className="ml-auto text-xs text-[var(--color-text-secondary)] font-medium">
                  {serviceTimings.length} service timings · {delays.length} of {delaysTotal} delays
                </div>
              </div>
            </Card>

            <Card padded={false} className="overflow-hidden">
              <div className="px-3 py-2 border-b border-[var(--color-border)] flex justify-between"><span className="text-sm font-semibold">Service timing — {legFilter.replace('_', ' ')}</span><span className="text-xs text-[var(--color-text-secondary)]">Scheduling and execution delay are separate from time taken</span></div>
              <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="bg-[var(--color-surface-muted)]"><th className="p-2">Service / Vessel</th><th className="p-2">Leg</th><th className="p-2 text-right">Scheduling gap</th><th className="p-2 text-right">Execution delay</th><th className="p-2">Time taken</th><th className="p-2">Status</th></tr></thead><tbody>{serviceTimings.slice(0, 12).map((row) => <tr key={row.service_request_id} className="border-t border-[var(--color-border)]"><td className="p-2 font-medium">{row.service_type}<span className="block text-[var(--color-text-tertiary)]">{row.vcn || row.vessel_name}</span></td><td className="p-2">{row.leg}</td><td className="p-2 text-right tabular-nums">{compactDuration(row.scheduling_gap_hours, true)}</td><td className="p-2 text-right tabular-nums">{compactDuration(row.execution_delay_hours, true)}</td><td className="p-2">{row.service_duration_hours == null ? 'Unavailable — no end timestamp' : `${row.service_duration_hours.toFixed(2)}h`}</td><td className="p-2"><StatusBadge label={`${row.execution_delay_status} · ${row.data_quality_status}`} tone={row.execution_delay_status === 'EARLY' ? 'good' : row.execution_delay_status === 'LATE' ? 'warning' : 'neutral'} /></td></tr>)}</tbody></table></div>
            </Card>

            {/* Delays Table */}
            <Card padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] border-b border-[var(--color-border)] font-semibold">
                      <th className="py-2.5 px-3">Delay ID</th>
                      <th className="py-2.5 px-3">VCN / Vessel</th>
                      <th className="py-2.5 px-3">Movement</th>
                      <th className="py-2.5 px-3">Duration</th>
                      <th className="py-2.5 px-3">Canonical Category</th>
                      <th className="py-2.5 px-3">Reason (Source Value)</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Allocations</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {delaysLoading ? (
                      <tr>
                        <td colSpan={9}>
                          <LoadingState label="Loading delays…" />
                        </td>
                      </tr>
                    ) : delays.length === 0 ? (
                      <tr>
                        <td colSpan={9}>
                          <EmptyState title="No delays match the filters" />
                        </td>
                      </tr>
                    ) : (
                      delays.map((d) => (
                        <tr key={d.id} className="hover:bg-[var(--color-surface-muted)] transition-colors">
                          <td className="py-2.5 px-3 font-mono font-medium text-[var(--color-text-primary)]">
                            {d.source_delay_id || d.id.slice(0, 8)}
                          </td>
                          <td className="py-2.5 px-3 font-medium text-[var(--color-text-primary)]">
                            {d.vcn}
                            <span className="text-[10px] text-[var(--color-text-tertiary)] block">{d.vessel_name}</span>
                          </td>
                          <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">{d.movement_stage}</td>
                          <td className="py-2.5 px-3 font-semibold text-[var(--color-warning)] tabular-nums">
                            {d.total_duration_hours}h
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="inline-block px-2 py-0.5 rounded-md text-[11px] font-medium bg-[var(--color-surface-muted)] text-[var(--color-text-primary)] border border-[var(--color-border)]">
                              {d.canonical_category}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-[var(--color-text-secondary)] max-w-xs truncate">
                            {d.delay_reason ? (
                              d.delay_reason
                            ) : (
                              <span className="text-[var(--color-critical)] italic font-semibold">
                                Missing Reason (DQ-007)
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <StatusBadge status={d.cause_status} showGlyph={false} />
                          </td>
                          <td className="py-2.5 px-3 text-[11px]">
                            {d.unallocated_duration_hours > 0 ? (
                              <span className="text-[var(--color-warning)] font-semibold">
                                {d.unallocated_duration_hours}h unallocated
                              </span>
                            ) : (
                              <span className="text-[var(--color-text-secondary)]">100% allocated</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right space-x-1 whitespace-nowrap">
                            {d.requires_reason_review && (
                              <button
                                onClick={() => {
                                  setReviewingDelay(d)
                                  setReviewCategory(d.canonical_category || 'Pilot')
                                  setReviewReason('')
                                }}
                                className="px-2 py-1 bg-[var(--color-critical)] hover:opacity-90 text-white rounded-md text-[11px] font-medium cursor-pointer"
                              >
                                Review DQ-007
                              </button>
                            )}
                            <button
                              onClick={() => handleOpenDetail(d.id)}
                              className="px-2 py-1 bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-[11px] font-medium cursor-pointer"
                            >
                              Allocations
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── Tab 2: Bottlenecks ──────────────────────────────────────────────── */}
        {activeTab === 'bottlenecks' && (
          <div className="space-y-4">
            <Card className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <p className="text-xs text-[var(--color-text-secondary)]">
                <span className="font-semibold text-[var(--color-text-primary)]">Governed Multi-Dimensional Ranking: </span>
                Bottlenecks are scored across Duration (15%), Frequency (20%), Variability CV (20%), Tail Risk TRR (20%),
                Turnaround Contribution (10%), and Target Breaches (15%).
                <strong className="text-[var(--color-critical)] ml-1">Ranking is not simply duration-ordered.</strong>
              </p>
              <select
                value={bnTypeFilter}
                onChange={(e) => setBnTypeFilter(e.target.value)}
                className={`${inputClass} shrink-0`}
              >
                <option value="">All Types (Resource & Process)</option>
                <option value="PROCESS_BOTTLENECK">Process Bottlenecks Only</option>
                <option value="RESOURCE_BOTTLENECK">Resource Bottlenecks Only</option>
              </select>
            </Card>

            {bnLoading ? (
              <Card>
                <LoadingState label="Loading bottleneck ranking…" />
              </Card>
            ) : bottlenecks.filter((b) => !bnTypeFilter || b.bottleneck_type === bnTypeFilter).length === 0 ? (
              <Card>
                <EmptyState title="No bottlenecks found" />
              </Card>
            ) : (
              <div className="space-y-3">
                {bottlenecks
                  .filter((b) => !bnTypeFilter || b.bottleneck_type === bnTypeFilter)
                  .map((b) => (
                    <Card key={b.stage_or_resource}>
                      <div className="flex flex-col md:flex-row md:items-center gap-4">
                        <div className="flex items-center gap-3 md:w-64 shrink-0">
                          <span className="text-lg font-bold text-[var(--color-text-tertiary)] tabular-nums w-8">
                            #{b.rank}
                          </span>
                          <div>
                            <div className="text-sm font-semibold text-[var(--color-text-primary)]">
                              {b.stage_or_resource}
                            </div>
                            <StatusBadge
                              label={b.bottleneck_type.replace('_', ' ')}
                              tone={b.bottleneck_type === 'RESOURCE_BOTTLENECK' ? 'warning' : 'neutral'}
                              showGlyph={false}
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 flex-1 text-xs">
                          <div>
                            <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                              Score
                            </div>
                            <div className="text-sm font-bold text-[var(--color-accent)] tabular-nums">
                              {b.overall_bottleneck_score}
                              <span className="text-[10px] font-normal text-[var(--color-text-tertiary)]"> / 100</span>
                            </div>
                          </div>
                          <div>
                            <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                              Mean Hours
                            </div>
                            <div className="font-medium text-[var(--color-text-primary)] tabular-nums">
                              {b.mean_hours}h
                            </div>
                          </div>
                          <div>
                            <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                              CV (Variability)
                            </div>
                            <div className="font-mono text-[var(--color-text-secondary)]">{b.cv}</div>
                          </div>
                          <div>
                            <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                              Tail Risk (P90/Med)
                            </div>
                            <div className="font-mono text-[var(--color-text-secondary)]">{b.tail_risk_ratio}x</div>
                          </div>
                          <div>
                            <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                              Target Breach
                            </div>
                            <div className="font-medium text-[var(--color-critical)] tabular-nums">
                              {Math.round(b.repeated_target_breach_rate * 100)}%
                            </div>
                          </div>
                        </div>

                        <div className="shrink-0 text-right text-xs">
                          <div className="text-[var(--color-text-tertiary)] uppercase text-[10px] tracking-wide">
                            Contribution
                          </div>
                          <div className="font-medium text-[var(--color-text-secondary)] tabular-nums">
                            {Math.round(b.turnaround_contribution * 100)}%
                          </div>
                        </div>
                      </div>
                    </Card>
                  ))}
              </div>
            )}
          </div>
        )}

        {/* ── Tab 3: Outliers ─────────────────────────────────────────────────── */}
        {activeTab === 'outliers' && (
          <div className="space-y-4">
            <Card padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)] border-b border-[var(--color-border)] font-semibold">
                      <th className="py-2.5 px-3">Category</th>
                      <th className="py-2.5 px-3">Vessel / VCN</th>
                      <th className="py-2.5 px-3">Metric / Issue</th>
                      <th className="py-2.5 px-3">Observed / Threshold</th>
                      <th className="py-2.5 px-3">Leg</th>
                      <th className="py-2.5 px-3">Severity</th>
                      <th className="py-2.5 px-3">State</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
                    {outliersLoading ? (
                      <tr>
                        <td colSpan={8}>
                          <LoadingState label="Detecting outliers…" />
                        </td>
                      </tr>
                    ) : outliers.length === 0 ? (
                      <tr>
                        <td colSpan={8}>
                          <EmptyState title="No outliers detected" />
                        </td>
                      </tr>
                    ) : (
                      outliers.map((o) => (
                        <tr key={o.id} className="hover:bg-[var(--color-surface-muted)] transition-colors">
                          <td className="py-2.5 px-3">
                            <span className="inline-block max-w-36 px-2 py-0.5 rounded-md text-[10px] leading-4 bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
                              {o.outlier_type}
                            </span>
                          </td>
                          <td className="py-2.5 px-3">
                            <p className="font-semibold text-[var(--color-text-primary)]">{o.vcn}</p>
                            {o.vessel_name && <p className="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">{o.vessel_name}</p>}
                          </td>
                          <td className="max-w-72 py-2.5 px-3">
                            <p className="font-medium text-[var(--color-text-primary)]">{o.metric_name}</p>
                            <p className="mt-0.5 text-[11px] leading-4 text-[var(--color-text-secondary)]">{o.issue_text || o.reason || 'Governed outlier detected.'}</p>
                            {o.rule_id && <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">{o.rule_id}</p>}
                          </td>
                          <td className="py-2.5 px-3">
                            <p className="font-semibold text-[var(--color-text-primary)] tabular-nums">{o.observed_value == null ? 'Unavailable' : `${o.observed_value}h`}</p>
                            <p className="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">{o.threshold_label || (o.benchmark_or_p90 == null ? 'No numeric benchmark' : `Threshold ${o.benchmark_or_p90}h`)}</p>
                          </td>
                          <td className="py-2.5 px-3 text-[var(--color-text-secondary)]">
                            {o.movement_leg ? o.movement_leg.replaceAll('_', ' / ') : 'All'}
                          </td>
                          <td className="py-2.5 px-3">
                            <StatusBadge label={o.severity} tone={severityTone(o.severity)} showGlyph={false} />
                          </td>
                          <td className="py-2.5 px-3">
                            <StatusBadge
                              label={o.is_excluded_from_kpi ? 'Excluded' : 'Included'}
                              tone={o.is_excluded_from_kpi ? 'critical' : 'good'}
                            />
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              onClick={() => {
                                setOutlierModal(o)
                                setExclusionRationale(o.exclusion_rationale || '')
                              }}
                              className="px-2 py-1 bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-[11px] font-medium cursor-pointer"
                            >
                              {o.is_excluded_from_kpi ? 'Re-include' : 'Exclude'}
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── Tab 4: Operational Criticality ──────────────────────────────────── */}
        {activeTab === 'criticality' && (
          <div className="space-y-4">
            <Card className="text-xs text-[var(--color-text-secondary)]">
              <span className="font-semibold text-[var(--color-text-primary)]">Spec §10.8 Operational Criticality: </span>
              Component scores for Duration (1-5), Variability (1-5), and Tail-Risk (1-5) must{' '}
              <strong className="text-[var(--color-accent)]">always be displayed alongside the overall score</strong>.
              Bands: 1.0–1.9 Low, 2.0–2.9 Moderate, 3.0–3.9 High, 4.0–5.0 Critical.
            </Card>

            {critLoading ? (
              <Card>
                <LoadingState label="Evaluating criticality…" />
              </Card>
            ) : criticalities.length === 0 ? (
              <Card>
                <EmptyState title="No criticality data available" />
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {criticalities.map((c) => (
                  <Card key={c.stage_name}>
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div>
                        <div className="text-sm font-semibold text-[var(--color-text-primary)]">{c.stage_name}</div>
                        <div className="text-[10px] text-[var(--color-text-tertiary)]">
                          {c.observations} calls observed
                        </div>
                      </div>
                      <StatusBadge label={c.band} tone={bandTone(c.band)} />
                    </div>

                    <div className="grid grid-cols-4 gap-2 text-center">
                      <div>
                        <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
                          Duration
                        </div>
                        <div className="text-sm font-bold text-[var(--color-text-primary)] tabular-nums">
                          {c.duration_score}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
                          Variability
                        </div>
                        <div className="text-sm font-bold text-[var(--color-text-primary)] tabular-nums">
                          {c.variability_score}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
                          Tail-Risk
                        </div>
                        <div className="text-sm font-bold text-[var(--color-text-primary)] tabular-nums">
                          {c.tail_risk_score}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)]">
                          Overall
                        </div>
                        <div className="text-sm font-extrabold text-[var(--color-accent)] tabular-nums">
                          {c.overall_score}
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Tab 5: Alerts & Actions ─────────────────────────────────────────── */}
        {activeTab === 'alerts' && (
          <div className="space-y-6">
            {/* Active Alerts List */}
            <Card padded={false}>
              <div className="px-4 py-3 border-b border-[var(--color-border)] flex justify-between items-center bg-[var(--color-surface-muted)]">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Active Operational Alerts ({alerts.length})
                </h3>
                <button
                  onClick={fetchAlertsAndActions}
                  className="text-xs px-2.5 py-1 bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-primary)] rounded-md font-medium cursor-pointer"
                >
                  Re-evaluate Rules
                </button>
              </div>
              <div className="divide-y divide-[var(--color-border)]">
                {alertsLoading ? (
                  <LoadingState label="Evaluating operational alert rules…" />
                ) : alerts.length === 0 ? (
                  <EmptyState title="No active operational alerts" />
                ) : (
                  alerts.map((a) => (
                    <div
                      key={a.id}
                      className="p-4 hover:bg-[var(--color-surface-muted)] transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <StatusBadge label={a.severity} tone={severityTone(a.severity)} showGlyph={false} />
                          <span className="text-xs font-mono text-[var(--color-text-tertiary)]">{a.rule_code}</span>
                          <StatusBadge status={a.status} showGlyph={false} />
                          {a.vcn && (
                            <span className="text-xs text-[var(--color-text-secondary)]">
                              Vessel Call: <span className="font-medium text-[var(--color-text-primary)]">{a.vcn}</span>
                            </span>
                          )}
                          {a.created_at && (
                            <span className="text-[10px] text-[var(--color-text-tertiary)]">
                              {new Date(a.created_at).toLocaleString()}
                            </span>
                          )}
                        </div>
                        <h4 className="text-sm font-semibold text-[var(--color-text-primary)]">{a.title}</h4>
                        <p className="text-xs text-[var(--color-text-secondary)]">{a.description}</p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {a.status === 'NEW' && (
                          <button
                            onClick={() => handleAcknowledgeAlert(a.id)}
                            className="px-2.5 py-1.5 bg-[var(--color-warning-bg)] hover:opacity-90 text-[var(--color-warning)] border border-[var(--color-warning-border)] rounded-md text-xs font-medium cursor-pointer"
                          >
                            Acknowledge
                          </button>
                        )}
                        {a.status !== 'RESOLVED' && (
                          <button
                            onClick={() => {
                              setResolvingAlert(a)
                              setResolveNotes('')
                            }}
                            className="px-2.5 py-1.5 bg-[var(--color-good)] hover:opacity-90 text-white rounded-md text-xs font-medium cursor-pointer"
                          >
                            Resolve
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setNewActionModal(a)
                            setNewActionTitle(`Mitigate ${a.title}`)
                            setNewActionDesc(a.description || '')
                          }}
                          className="px-2.5 py-1.5 bg-[var(--color-accent-soft)] hover:opacity-90 text-[var(--color-accent)] border border-[var(--color-accent-soft-border)] rounded-md text-xs font-medium cursor-pointer"
                        >
                          Create Action
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>

            {/* Action Items List */}
            <Card padded={false}>
              <div className="px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                  Remediation Action Items ({actionItems.length})
                </h3>
              </div>
              <div className="divide-y divide-[var(--color-border)]">
                {actionItems.length === 0 ? (
                  <EmptyState title="No active remediation action items" />
                ) : (
                  actionItems.map((act) => (
                    <div key={act.id} className="p-3.5 flex items-center justify-between text-xs gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="font-semibold text-[var(--color-text-primary)]">{act.title}</span>
                          <span className="px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-[var(--color-surface-muted)] text-[var(--color-text-secondary)]">
                            {act.priority}
                          </span>
                          <span className="text-[10px] text-[var(--color-accent)] font-semibold">{act.status}</span>
                        </div>
                        <p className="text-[var(--color-text-secondary)]">{act.description}</p>
                      </div>
                      <div className="text-right text-[var(--color-text-tertiary)] text-[11px] shrink-0">
                        <span>Assigned: {act.assigned_to || 'Unassigned'}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        )}
      </div>

      {/* ── Modal: Delay Allocations & Split ─────────────────────────────────── */}
      {selectedDelay && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl max-w-2xl w-full p-5 space-y-4 shadow-xl">
            <div className="flex justify-between items-start border-b border-[var(--color-border)] pb-3">
              <div>
                <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
                  Delay Allocations: {selectedDelay.source_delay_id || selectedDelay.id.slice(0, 8)} ({selectedDelay.vcn})
                </h3>
                <span className="text-xs text-[var(--color-text-secondary)]">
                  Total Delay: {selectedDelay.total_duration_hours}h | Unallocated: {selectedDelay.unallocated_duration_hours}h
                </span>
              </div>
              <button
                onClick={() => setSelectedDelay(null)}
                className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-sm cursor-pointer"
              >
                <X size={15} aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-3 max-h-96 overflow-y-auto">
              <h4 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
                Allocated Causes
              </h4>
              {selectedDelay.allocations.length === 0 ? (
                <EmptyState title="No allocations recorded" />
              ) : (
                selectedDelay.allocations.map((a) => (
                  <div
                    key={a.id}
                    className="p-3 bg-[var(--color-surface-muted)] rounded-md border border-[var(--color-border)] space-y-1"
                  >
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-[var(--color-text-primary)]">
                        {a.canonical_category}{' '}
                        {a.is_primary && <span className="text-[var(--color-accent)] text-[10px]">(Primary)</span>}
                      </span>
                      <span className="font-semibold text-[var(--color-warning)] tabular-nums">{a.duration_hours}h</span>
                    </div>
                    <p className="text-xs text-[var(--color-text-secondary)]">{a.reason || 'No detailed reason text'}</p>
                    <div className="flex gap-2 text-[10px] text-[var(--color-text-tertiary)] pt-1">
                      <span>Status: {a.cause_status}</span>
                      <span>Review: {a.human_review_state}</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="flex justify-between items-center pt-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => handleInferCause(selectedDelay.id)}
                className="px-3 py-1.5 bg-[var(--color-inferred-bg)] hover:opacity-90 text-[var(--color-inferred)] border border-[var(--color-inferred-border)] rounded-md text-xs font-medium cursor-pointer"
              >
                Trigger Evidence Inference
              </button>
              <button
                onClick={() => setSelectedDelay(null)}
                className="px-4 py-1.5 bg-[var(--color-surface-muted)] hover:bg-[var(--color-border)] text-[var(--color-text-primary)] rounded-md text-xs font-medium cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Review DQ-007 ────────────────────────────────────────────── */}
      {reviewingDelay && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
              Mandatory Delay Reason Review (DQ-007)
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)]">
              Vessel <span className="font-semibold text-[var(--color-text-primary)]">{reviewingDelay.vcn}</span>{' '}
              experienced {reviewingDelay.total_duration_hours}h delay on {reviewingDelay.movement_stage} without reason
              or category documentation.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-medium text-[var(--color-text-secondary)] block mb-1">
                  Assign Canonical Category
                </label>
                <select
                  value={reviewCategory}
                  onChange={(e) => setReviewCategory(e.target.value)}
                  className={`w-full ${inputClass}`}
                >
                  <option value="Pilot">Pilot</option>
                  <option value="Tug">Tug</option>
                  <option value="Berth Non-Availability">Berth Non-Availability</option>
                  <option value="Weather">Weather</option>
                  <option value="Terminal Readiness">Terminal Readiness</option>
                  <option value="Vessel-Side">Vessel-Side</option>
                  <option value="Documentation">Documentation</option>
                </select>
              </div>

              <div>
                <label className="font-medium text-[var(--color-text-secondary)] block mb-1">
                  Documented Delay Reason
                </label>
                <textarea
                  rows={3}
                  value={reviewReason}
                  onChange={(e) => setReviewReason(e.target.value)}
                  placeholder="Enter documented cause determined during harbor review..."
                  className={`w-full ${inputClass}`}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => setReviewingDelay(null)}
                className="px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] rounded-md cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleReviewSubmit}
                disabled={!reviewReason.trim()}
                className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 text-white rounded-md text-xs font-semibold cursor-pointer"
              >
                Approve & Resolve DQ-007
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Outlier Exclusion ────────────────────────────────────────── */}
      {outlierModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
              {outlierModal.is_excluded_from_kpi ? 'Re-include Outlier in KPIs' : 'Exclude Outlier from KPIs'}
            </h3>
            <p className="text-xs text-[var(--color-text-secondary)]">
              Vessel <span className="font-semibold text-[var(--color-text-primary)]">{outlierModal.vcn}</span>:{' '}
              {outlierModal.metric_name} observed {outlierModal.observed_value == null ? 'an unavailable numeric value' : `${outlierModal.observed_value}h`}
              {outlierModal.divergence == null ? '.' : ` (divergence ${outlierModal.divergence}h).`}
            </p>
            {(outlierModal.issue_text || outlierModal.reason) && (
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 text-xs text-[var(--color-text-secondary)]">
                <p className="font-medium text-[var(--color-text-primary)]">{outlierModal.issue_text}</p>
                {outlierModal.reason && <p className="mt-1">{outlierModal.reason}</p>}
                {outlierModal.threshold_label && <p className="mt-1 font-medium">{outlierModal.threshold_label}</p>}
              </div>
            )}

            <div className="space-y-2 text-xs">
              <label className="font-medium text-[var(--color-text-secondary)] block">Governance Rationale</label>
              <textarea
                rows={3}
                value={exclusionRationale}
                onChange={(e) => setExclusionRationale(e.target.value)}
                placeholder="State reason for excluding/including this outlier in KPI baselines..."
                className={`w-full ${inputClass}`}
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => setOutlierModal(null)}
                className="px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] rounded-md cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleToggleExclusion}
                className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md text-xs font-semibold cursor-pointer"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Resolve Alert ────────────────────────────────────────────── */}
      {resolvingAlert && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Resolve Operational Alert</h3>
            <p className="text-xs text-[var(--color-text-secondary)]">{resolvingAlert.title}</p>

            <div className="space-y-2 text-xs">
              <label className="font-medium text-[var(--color-text-secondary)] block">Resolution Notes</label>
              <textarea
                rows={3}
                value={resolveNotes}
                onChange={(e) => setResolveNotes(e.target.value)}
                placeholder="Document resolution action taken..."
                className={`w-full ${inputClass}`}
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => setResolvingAlert(null)}
                className="px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] rounded-md cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveAlert}
                disabled={!resolveNotes.trim()}
                className="px-4 py-1.5 bg-[var(--color-good)] hover:opacity-90 disabled:opacity-50 text-white rounded-md text-xs font-semibold cursor-pointer"
              >
                Confirm Resolution
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Create Action Item ──────────────────────────────────────── */}
      {newActionModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Create Action Item</h3>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-medium text-[var(--color-text-secondary)] block mb-1">Title</label>
                <input
                  type="text"
                  value={newActionTitle}
                  onChange={(e) => setNewActionTitle(e.target.value)}
                  className={`w-full ${inputClass}`}
                />
              </div>

              <div>
                <label className="font-medium text-[var(--color-text-secondary)] block mb-1">Description</label>
                <textarea
                  rows={2}
                  value={newActionDesc}
                  onChange={(e) => setNewActionDesc(e.target.value)}
                  className={`w-full ${inputClass}`}
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="font-medium text-[var(--color-text-secondary)] block mb-1">Assignee</label>
                  <input
                    type="text"
                    value={newActionAssignee}
                    onChange={(e) => setNewActionAssignee(e.target.value)}
                    placeholder="e.g. pilot_dispatcher"
                    className={`w-full ${inputClass}`}
                  />
                </div>
                <div>
                  <label className="font-medium text-[var(--color-text-secondary)] block mb-1">Priority</label>
                  <select
                    value={newActionPriority}
                    onChange={(e) => setNewActionPriority(e.target.value)}
                    className={`w-full ${inputClass}`}
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="URGENT">Urgent</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-[var(--color-border)]">
              <button
                onClick={() => setNewActionModal(null)}
                className="px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] rounded-md cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateAction}
                disabled={!newActionTitle.trim()}
                className="px-4 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 text-white rounded-md text-xs font-semibold cursor-pointer"
              >
                Create Task
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
