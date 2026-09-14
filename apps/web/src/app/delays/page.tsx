'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../../lib/auth-context'

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
  metric_name: string
  observed_value: number
  benchmark_or_p90?: number
  divergence?: number
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

export default function DelaysAndBottlenecksPage() {
  const { token } = useAuth()
  const [activeTab, setActiveTab] = useState<TabType>('delays')

  // Summary & Delays state
  const [summary, setSummary] = useState<DelaysSummary | null>(null)
  const [delays, setDelays] = useState<DelayItem[]>([])
  const [delaysTotal, setDelaysTotal] = useState(0)
  const [delaysLoading, setDelaysLoading] = useState(false)
  const [stageFilter, setStageFilter] = useState('')
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
    if (!token) return
    try {
      const res = await fetch(`${API}/api/v1/delays/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setSummary(data)
      }
    } catch (e) {
      console.error('Failed to load delays summary', e)
    }
  }, [token])

  // 2. Fetch Delays List
  const fetchDelays = useCallback(async () => {
    if (!token) return
    setDelaysLoading(true)
    try {
      const params = new URLSearchParams()
      if (stageFilter) params.append('stage', stageFilter)
      if (categoryFilter) params.append('category', categoryFilter)
      if (causeStatusFilter) params.append('cause_status', causeStatusFilter)
      if (searchQuery) params.append('search', searchQuery)
      if (reviewFilter !== null) params.append('requires_review', String(reviewFilter))
      params.append('limit', '100')

      const res = await fetch(`${API}/api/v1/delays?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setDelays(data.items || [])
        setDelaysTotal(data.total || 0)
      }
    } catch (e) {
      console.error('Failed to load delays', e)
    } finally {
      setDelaysLoading(false)
    }
  }, [token, stageFilter, categoryFilter, causeStatusFilter, searchQuery, reviewFilter])

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
    fetchSummary()
    fetchDelays()
  }, [fetchSummary, fetchDelays])

  useEffect(() => {
    if (activeTab === 'bottlenecks') fetchBottlenecks()
    if (activeTab === 'outliers') fetchOutliers()
    if (activeTab === 'criticality') fetchCriticality()
    if (activeTab === 'alerts') fetchAlertsAndActions()
  }, [activeTab, fetchBottlenecks, fetchOutliers, fetchCriticality, fetchAlertsAndActions])

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

  return (
    <div className="space-y-6">
      {/* 1. Header & Quick Summary */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Delays, Bottlenecks & Operational Risk
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Governed delay cause attribution, non-duration bottleneck ranking, outlier detection (DQ-008),
            criticality component scoring, and alerts workflow.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Active Governed Engine
          </span>
        </div>
      </div>

      {/* 2. Top Summary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">Total Delays</span>
          <div className="text-2xl font-bold text-slate-900 mt-1">
            {summary ? summary.total_delays : '—'}
          </div>
          <span className="text-[10px] text-slate-500">41 fixture delays</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">Delay Hours</span>
          <div className="text-2xl font-bold text-amber-600 mt-1">
            {summary ? `${summary.total_delay_hours}h` : '—'}
          </div>
          <span className="text-[10px] text-slate-500">Sum of durations</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">Confirmed vs Inferred</span>
          <div className="text-2xl font-bold text-slate-800 mt-1">
            {summary ? `${summary.confirmed_count} / ${summary.inferred_count}` : '—'}
          </div>
          <span className="text-[10px] text-slate-500">Confirmed / Inferred</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">Unallocated Time</span>
          <div className="text-2xl font-bold text-slate-700 mt-1">
            {summary ? `${summary.total_unallocated_hours}h` : '—'}
          </div>
          <span className="text-[10px] text-slate-500">Remainder explicit</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">Reconciled Clean</span>
          <div className="text-2xl font-bold text-emerald-600 mt-1">
            {summary ? `${summary.total_delays - summary.reconciliation_mismatches_count} / ${summary.total_delays}` : '—'}
          </div>
          <span className="text-[10px] text-slate-500">Served − Sched ±0.02h</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
          <span className="text-[11px] font-medium text-slate-400 block uppercase tracking-wider">DQ-007 Reviews</span>
          <div className="text-2xl font-bold text-rose-600 mt-1">
            {summary ? summary.review_required_count : '—'}
          </div>
          <span className="text-[10px] text-rose-500">Requires reason</span>
        </div>
      </div>

      {/* 3. Navigation Tabs */}
      <div className="flex border-b border-slate-200 gap-1 text-sm font-medium">
        {[
          { id: 'delays' as TabType, label: 'Delay Causes & Pareto' },
          { id: 'bottlenecks' as TabType, label: 'Bottleneck Scoring' },
          { id: 'outliers' as TabType, label: 'Outliers & DQ-008' },
          { id: 'criticality' as TabType, label: 'Operational Criticality' },
          { id: 'alerts' as TabType, label: 'Alerts & Actions' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 border-b-2 font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-indigo-600 text-indigo-600 font-semibold'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab 1: Delay Causes & Pareto ────────────────────────────────────── */}
      {activeTab === 'delays' && (
        <div className="space-y-6">
          {/* Pareto Distribution Cards */}
          {summary && summary.pareto_categories.length > 0 && (
            <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
              <h3 className="text-sm font-bold text-slate-900 mb-2">Delay Cause Pareto Distribution</h3>
              <p className="text-xs text-slate-500 mb-4">
                Canonical delay category contribution ranked by total impact hours with cumulative share.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                {summary.pareto_categories.slice(0, 4).map((cat, idx) => (
                  <div key={cat.category} className="p-3 bg-slate-50 rounded border border-slate-200">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-bold text-slate-700">#{idx + 1} {cat.category}</span>
                      <span className="text-indigo-600 font-semibold">{cat.total_hours}h</span>
                    </div>
                    <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mt-2">
                      <div
                        className="bg-indigo-600 h-full rounded-full"
                        style={{ width: `${Math.min(100, cat.cumulative_percentage)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                      <span>{cat.count} occurrences</span>
                      <span>{cat.cumulative_percentage}% cumulative</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2 bg-white p-3 rounded-lg border border-slate-200">
            <input
              type="text"
              placeholder="Search VCN, reason, vessel..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="text-xs px-3 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 w-56"
            />
            <select
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
              className="text-xs px-3 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
            >
              <option value="">All Movement Stages</option>
              <option value="Arrival">Arrival</option>
              <option value="Sailing">Sailing</option>
              <option value="Shifting">Shifting</option>
            </select>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="text-xs px-3 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
            >
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
            <select
              value={causeStatusFilter}
              onChange={(e) => setCauseStatusFilter(e.target.value)}
              className="text-xs px-3 py-1.5 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
            >
              <option value="">All Cause Statuses</option>
              <option value="Confirmed">Confirmed</option>
              <option value="Inferred">Inferred</option>
            </select>
            <button
              onClick={() => setReviewFilter(reviewFilter === true ? null : true)}
              className={`text-xs px-2.5 py-1.5 rounded border transition-colors ${
                reviewFilter === true
                  ? 'bg-rose-50 border-rose-300 text-rose-700 font-semibold'
                  : 'bg-white border-slate-300 text-slate-600 hover:bg-slate-50'
              }`}
            >
              Missing Reason Review (DQ-007)
            </button>
            <div className="ml-auto text-xs text-slate-500 font-medium">
              Showing {delays.length} of {delaysTotal} delays
            </div>
          </div>

          {/* Delays Table */}
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
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
                <tbody className="divide-y divide-slate-100">
                  {delaysLoading ? (
                    <tr>
                      <td colSpan={9} className="py-8 text-center text-slate-400">Loading delays...</td>
                    </tr>
                  ) : delays.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-8 text-center text-slate-400">No delays match the filters.</td>
                    </tr>
                  ) : (
                    delays.map((d) => (
                      <tr key={d.id} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2.5 px-3 font-mono font-medium text-slate-900">{d.source_delay_id || d.id.slice(0, 8)}</td>
                        <td className="py-2.5 px-3 font-medium text-slate-800">
                          {d.vcn}
                          <span className="text-[10px] text-slate-400 block">{d.vessel_name}</span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-600">{d.movement_stage}</td>
                        <td className="py-2.5 px-3 font-bold text-amber-600">{d.total_duration_hours}h</td>
                        <td className="py-2.5 px-3">
                          <span className="inline-block px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-800 border border-slate-200">
                            {d.canonical_category}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-700 max-w-xs truncate">
                          {d.delay_reason ? (
                            d.delay_reason
                          ) : (
                            <span className="text-rose-500 italic font-semibold">Missing Reason (DQ-007)</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                              d.cause_status.toLowerCase() === 'confirmed'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-purple-100 text-purple-800 border border-purple-200'
                            }`}
                          >
                            {d.cause_status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                          {d.unallocated_duration_hours > 0 ? (
                            <span className="text-amber-600 font-semibold">{d.unallocated_duration_hours}h unallocated</span>
                          ) : (
                            <span className="text-slate-600">100% allocated</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right space-x-1">
                          {d.requires_reason_review && (
                            <button
                              onClick={() => {
                                setReviewingDelay(d)
                                setReviewCategory(d.canonical_category || 'Pilot')
                                setReviewReason('')
                              }}
                              className="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded text-[11px] font-medium"
                            >
                              Review DQ-007
                            </button>
                          )}
                          <button
                            onClick={() => handleOpenDetail(d.id)}
                            className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-[11px] font-medium"
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
          </div>
        </div>
      )}

      {/* ── Tab 2: Bottlenecks ──────────────────────────────────────────────── */}
      {activeTab === 'bottlenecks' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white p-3 rounded-lg border border-slate-200">
            <div className="text-xs text-slate-600">
              <span className="font-semibold text-slate-900">Governed Multi-Dimensional Ranking:</span> Bottlenecks are scored across
              Duration (15%), Frequency (20%), Variability CV (20%), Tail Risk TRR (20%), Turnaround Contribution (10%), and Target Breaches (15%).
              <strong className="text-rose-600 ml-1">Ranking is not simply duration-ordered.</strong>
            </div>
            <div className="flex gap-2">
              <select
                value={bnTypeFilter}
                onChange={(e) => setBnTypeFilter(e.target.value)}
                className="text-xs px-3 py-1.5 border border-slate-300 rounded-md bg-white"
              >
                <option value="">All Types (Resource & Process)</option>
                <option value="PROCESS_BOTTLENECK">Process Bottlenecks Only</option>
                <option value="RESOURCE_BOTTLENECK">Resource Bottlenecks Only</option>
              </select>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
                  <th className="py-2.5 px-3">Rank</th>
                  <th className="py-2.5 px-3">Stage / Resource</th>
                  <th className="py-2.5 px-3">Classification</th>
                  <th className="py-2.5 px-3 text-right">Bottleneck Score</th>
                  <th className="py-2.5 px-3 text-right">Mean Hours</th>
                  <th className="py-2.5 px-3 text-right">CV (Variability)</th>
                  <th className="py-2.5 px-3 text-right">Tail Risk (P90/Med)</th>
                  <th className="py-2.5 px-3 text-right">Target Breach Rate</th>
                  <th className="py-2.5 px-3 text-right">Contribution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {bnLoading ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-slate-400">Loading bottleneck ranking...</td>
                  </tr>
                ) : (
                  bottlenecks
                    .filter((b) => !bnTypeFilter || b.bottleneck_type === bnTypeFilter)
                    .map((b) => (
                      <tr key={b.stage_or_resource} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2.5 px-3 font-bold text-slate-800">#{b.rank}</td>
                        <td className="py-2.5 px-3 font-semibold text-slate-900">{b.stage_or_resource}</td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                              b.bottleneck_type === 'RESOURCE_BOTTLENECK'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-blue-100 text-blue-800'
                            }`}
                          >
                            {b.bottleneck_type.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <span className="font-bold text-sm text-indigo-700">{b.overall_bottleneck_score}</span>
                          <span className="text-[10px] text-slate-400 block">/ 100</span>
                        </td>
                        <td className="py-2.5 px-3 text-right font-medium text-slate-800">{b.mean_hours}h</td>
                        <td className="py-2.5 px-3 text-right font-mono text-slate-700">{b.cv}</td>
                        <td className="py-2.5 px-3 text-right font-mono text-slate-700">{b.tail_risk_ratio}x</td>
                        <td className="py-2.5 px-3 text-right font-medium text-rose-600">
                          {Math.round(b.repeated_target_breach_rate * 100)}%
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-600">
                          {Math.round(b.turnaround_contribution * 100)}%
                        </td>
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Tab 3: Outliers & DQ-008 ────────────────────────────────────────── */}
      {activeTab === 'outliers' && (
        <div className="space-y-4">
          <div className="bg-amber-50 border border-amber-200 p-4 rounded-lg">
            <h3 className="text-sm font-bold text-amber-900 mb-1">Deliberate Oracle Case: DQ-008 (SYNVCN2600063)</h3>
            <p className="text-xs text-amber-800">
              Vessel call <code className="bg-amber-100 px-1 py-0.5 rounded">SYNVCN2600063</code> has an oracle turnaround of 720 hours
              against calculated 86.5h. The engine identifies this as an extreme operational outlier and provides transparent exclusion
              toggle to safeguard KPI production baselines.
            </p>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
                  <th className="py-2.5 px-3">VCN / Vessel</th>
                  <th className="py-2.5 px-3">Metric Name</th>
                  <th className="py-2.5 px-3">Outlier Classification</th>
                  <th className="py-2.5 px-3 text-right">Observed</th>
                  <th className="py-2.5 px-3 text-right">Benchmark / P90</th>
                  <th className="py-2.5 px-3 text-right">Divergence</th>
                  <th className="py-2.5 px-3">Severity</th>
                  <th className="py-2.5 px-3">KPI Exclusion State</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {outliersLoading ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-slate-400">Detecting outliers...</td>
                  </tr>
                ) : (
                  outliers.map((o) => (
                    <tr key={o.id} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2.5 px-3 font-semibold text-slate-900">{o.vcn}</td>
                      <td className="py-2.5 px-3 font-medium text-slate-800">{o.metric_name}</td>
                      <td className="py-2.5 px-3">
                        <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-700">
                          {o.outlier_type}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right font-bold text-slate-900">{o.observed_value}h</td>
                      <td className="py-2.5 px-3 text-right text-slate-600">{o.benchmark_or_p90 || '—'}h</td>
                      <td className="py-2.5 px-3 text-right font-bold text-rose-600">+{o.divergence || 0}h</td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                            o.severity === 'CRITICAL'
                              ? 'bg-rose-100 text-rose-800'
                              : o.severity === 'HIGH'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-blue-100 text-blue-800'
                          }`}
                        >
                          {o.severity}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        {o.is_excluded_from_kpi ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                            EXCLUDED
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            INCLUDED
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => {
                            setOutlierModal(o)
                            setExclusionRationale(o.exclusion_rationale || '')
                          }}
                          className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-[11px] font-medium"
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
        </div>
      )}

      {/* ── Tab 4: Operational Criticality ──────────────────────────────────── */}
      {activeTab === 'criticality' && (
        <div className="space-y-4">
          <div className="bg-white p-3 rounded-lg border border-slate-200 text-xs text-slate-600">
            <span className="font-semibold text-slate-900">Spec §10.8 Operational Criticality:</span> Component scores for Duration (1-5),
            Variability (1-5), and Tail-Risk (1-5) must <strong className="text-indigo-600">always be displayed alongside the overall score</strong>.
            Bands: 1.0–1.9 Low, 2.0–2.9 Moderate, 3.0–3.9 High, 4.0–5.0 Critical.
          </div>

          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
                  <th className="py-2.5 px-3">Stage / Lead Time</th>
                  <th className="py-2.5 px-3 text-center">Duration Score (1–5)</th>
                  <th className="py-2.5 px-3 text-center">Variability Score (1–5)</th>
                  <th className="py-2.5 px-3 text-center">Tail-Risk Score (1–5)</th>
                  <th className="py-2.5 px-3 text-right">Overall Score</th>
                  <th className="py-2.5 px-3 text-right">Criticality Band</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {critLoading ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-400">Evaluating criticality...</td>
                  </tr>
                ) : (
                  criticalities.map((c) => (
                    <tr key={c.stage_name} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2.5 px-3 font-semibold text-slate-900">
                        {c.stage_name}
                        <span className="text-[10px] text-slate-400 block">{c.observations} calls observed</span>
                      </td>
                      <td className="py-2.5 px-3 text-center font-bold text-slate-700">{c.duration_score}</td>
                      <td className="py-2.5 px-3 text-center font-bold text-slate-700">{c.variability_score}</td>
                      <td className="py-2.5 px-3 text-center font-bold text-slate-700">{c.tail_risk_score}</td>
                      <td className="py-2.5 px-3 text-right font-extrabold text-sm text-indigo-700">{c.overall_score}</td>
                      <td className="py-2.5 px-3 text-right">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-bold ${
                            c.band === 'CRITICAL'
                              ? 'bg-rose-100 text-rose-800 border border-rose-200'
                              : c.band === 'HIGH'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : c.band === 'MODERATE'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {c.band}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Tab 5: Alerts & Actions ─────────────────────────────────────────── */}
      {activeTab === 'alerts' && (
        <div className="space-y-6">
          {/* Active Alerts List */}
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-slate-200 flex justify-between items-center bg-slate-50">
              <h3 className="text-sm font-bold text-slate-900">Active Operational Alerts ({alerts.length})</h3>
              <button
                onClick={fetchAlertsAndActions}
                className="text-xs px-2.5 py-1 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 rounded font-medium shadow-sm"
              >
                Re-evaluate Rules
              </button>
            </div>
            <div className="divide-y divide-slate-100">
              {alertsLoading ? (
                <div className="p-8 text-center text-slate-400 text-xs">Evaluating operational alert rules...</div>
              ) : alerts.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-xs">No active operational alerts.</div>
              ) : (
                alerts.map((a) => (
                  <div key={a.id} className="p-4 hover:bg-slate-50 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            a.severity === 'CRITICAL'
                              ? 'bg-rose-100 text-rose-800'
                              : a.severity === 'HIGH'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-blue-100 text-blue-800'
                          }`}
                        >
                          {a.severity}
                        </span>
                        <span className="text-xs font-mono text-slate-400">{a.rule_code}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            a.status === 'NEW'
                              ? 'bg-purple-100 text-purple-800'
                              : a.status === 'ACKNOWLEDGED'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {a.status}
                        </span>
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">{a.title}</h4>
                      <p className="text-xs text-slate-600">{a.description}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {a.status === 'NEW' && (
                        <button
                          onClick={() => handleAcknowledgeAlert(a.id)}
                          className="px-2.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded text-xs font-medium"
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
                          className="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-medium"
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
                        className="px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded text-xs font-medium"
                      >
                        Create Action
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Action Items List */}
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden shadow-sm">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold text-slate-900">Remediation Action Items ({actionItems.length})</h3>
            </div>
            <div className="divide-y divide-slate-100">
              {actionItems.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-xs">No active remediation action items.</div>
              ) : (
                actionItems.map((act) => (
                  <div key={act.id} className="p-3.5 flex items-center justify-between text-xs">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-slate-900">{act.title}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                          {act.priority}
                        </span>
                        <span className="text-[10px] text-indigo-600 font-semibold">{act.status}</span>
                      </div>
                      <p className="text-slate-500">{act.description}</p>
                    </div>
                    <div className="text-right text-slate-400 text-[11px]">
                      <span>Assigned: {act.assigned_to || 'Unassigned'}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Delay Allocations & Split ─────────────────────────────────── */}
      {selectedDelay && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-2xl w-full p-5 space-y-4 shadow-xl">
            <div className="flex justify-between items-start border-b border-slate-200 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Delay Allocations: {selectedDelay.source_delay_id || selectedDelay.id.slice(0, 8)} ({selectedDelay.vcn})
                </h3>
                <span className="text-xs text-slate-500">
                  Total Delay: {selectedDelay.total_duration_hours}h | Unallocated: {selectedDelay.unallocated_duration_hours}h
                </span>
              </div>
              <button onClick={() => setSelectedDelay(null)} className="text-slate-400 hover:text-slate-600 text-sm">
                ✕
              </button>
            </div>

            <div className="space-y-3 max-h-96 overflow-y-auto">
              <h4 className="text-xs font-bold text-slate-700 uppercase">Allocated Causes</h4>
              {selectedDelay.allocations.map((a) => (
                <div key={a.id} className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-bold text-slate-800">
                      {a.canonical_category} {a.is_primary && <span className="text-indigo-600 text-[10px]">(Primary)</span>}
                    </span>
                    <span className="font-bold text-amber-600">{a.duration_hours}h</span>
                  </div>
                  <p className="text-xs text-slate-600">{a.reason || 'No detailed reason text'}</p>
                  <div className="flex gap-2 text-[10px] text-slate-400 pt-1">
                    <span>Status: {a.cause_status}</span>
                    <span>Review: {a.human_review_state}</span>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-between items-center pt-3 border-t border-slate-200">
              <button
                onClick={() => handleInferCause(selectedDelay.id)}
                className="px-3 py-1.5 bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 rounded text-xs font-medium"
              >
                Trigger Evidence Inference
              </button>
              <button
                onClick={() => setSelectedDelay(null)}
                className="px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-medium"
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
          <div className="bg-white rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">
              Mandatory Delay Reason Review (DQ-007)
            </h3>
            <p className="text-xs text-slate-500">
              Vessel <span className="font-bold text-slate-700">{reviewingDelay.vcn}</span> experienced {reviewingDelay.total_duration_hours}h
              delay on {reviewingDelay.movement_stage} without reason or category documentation.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-medium text-slate-700 block mb-1">Assign Canonical Category</label>
                <select
                  value={reviewCategory}
                  onChange={(e) => setReviewCategory(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded bg-white"
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
                <label className="font-medium text-slate-700 block mb-1">Documented Delay Reason</label>
                <textarea
                  rows={3}
                  value={reviewReason}
                  onChange={(e) => setReviewReason(e.target.value)}
                  placeholder="Enter documented cause determined during harbor review..."
                  className="w-full px-3 py-1.5 border border-slate-300 rounded"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setReviewingDelay(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleReviewSubmit}
                disabled={!reviewReason.trim()}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded text-xs font-semibold"
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
          <div className="bg-white rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">
              {outlierModal.is_excluded_from_kpi ? 'Re-include Outlier in KPIs' : 'Exclude Outlier from KPIs'}
            </h3>
            <p className="text-xs text-slate-500">
              Vessel <span className="font-bold text-slate-700">{outlierModal.vcn}</span>: {outlierModal.metric_name} observed {outlierModal.observed_value}h
              (divergence +{outlierModal.divergence}h).
            </p>

            <div className="space-y-2 text-xs">
              <label className="font-medium text-slate-700 block">Governance Rationale</label>
              <textarea
                rows={3}
                value={exclusionRationale}
                onChange={(e) => setExclusionRationale(e.target.value)}
                placeholder="State reason for excluding/including this outlier in KPI baselines..."
                className="w-full px-3 py-1.5 border border-slate-300 rounded"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setOutlierModal(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleToggleExclusion}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded text-xs font-semibold"
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
          <div className="bg-white rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">Resolve Operational Alert</h3>
            <p className="text-xs text-slate-500">{resolvingAlert.title}</p>

            <div className="space-y-2 text-xs">
              <label className="font-medium text-slate-700 block">Resolution Notes</label>
              <textarea
                rows={3}
                value={resolveNotes}
                onChange={(e) => setResolveNotes(e.target.value)}
                placeholder="Document resolution action taken..."
                className="w-full px-3 py-1.5 border border-slate-300 rounded"
              />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setResolvingAlert(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveAlert}
                disabled={!resolveNotes.trim()}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded text-xs font-semibold"
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
          <div className="bg-white rounded-xl max-w-md w-full p-5 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">Create Action Item</h3>

            <div className="space-y-3 text-xs">
              <div>
                <label className="font-medium text-slate-700 block mb-1">Title</label>
                <input
                  type="text"
                  value={newActionTitle}
                  onChange={(e) => setNewActionTitle(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded"
                />
              </div>

              <div>
                <label className="font-medium text-slate-700 block mb-1">Description</label>
                <textarea
                  rows={2}
                  value={newActionDesc}
                  onChange={(e) => setNewActionDesc(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-300 rounded"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="font-medium text-slate-700 block mb-1">Assignee</label>
                  <input
                    type="text"
                    value={newActionAssignee}
                    onChange={(e) => setNewActionAssignee(e.target.value)}
                    placeholder="e.g. pilot_dispatcher"
                    className="w-full px-3 py-1.5 border border-slate-300 rounded"
                  />
                </div>
                <div>
                  <label className="font-medium text-slate-700 block mb-1">Priority</label>
                  <select
                    value={newActionPriority}
                    onChange={(e) => setNewActionPriority(e.target.value)}
                    className="w-full px-3 py-1.5 border border-slate-300 rounded bg-white"
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="URGENT">Urgent</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
              <button
                onClick={() => setNewActionModal(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateAction}
                disabled={!newActionTitle.trim()}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded text-xs font-semibold"
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
