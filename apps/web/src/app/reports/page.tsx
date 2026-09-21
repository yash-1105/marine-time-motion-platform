'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { CalendarClock, FileChartColumn, Play, X } from 'lucide-react'
import { Card, EmptyState, LoadingState, PageHeader, StatusBadge } from '@/components/ui'
import { useAuth } from '@/lib/auth-context'

const api = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1'
type Template = { template_id: string; name: string; version: string; status: string; sections: string[] }
type Run = { report_run_id: string; status: string; progress: number; template_id: string; formats: string[]; failure_reason?: string | null; version: number }
type ReportResult = { report_run_id: string; status: string; result: { metadata: Record<string, unknown>; sections: Record<string, { title: string; value: unknown }> } }

function pretty(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) }

export default function ReportsPage() {
  const { token } = useAuth()
  const headers = useMemo(() => ({ Authorization: `Bearer ${token || 'dev-token'}` }), [token])
  const [templates, setTemplates] = useState<Template[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [selected, setSelected] = useState<ReportResult | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [tr, rr] = await Promise.all([fetch(`${api}/reports/templates`, { headers }), fetch(`${api}/reports/runs`, { headers })])
      if (!tr.ok || !rr.ok) throw new Error('Unable to load reporting data.')
      const [td, rd] = await Promise.all([tr.json(), rr.json()])
      if (!Array.isArray(td) || !Array.isArray(rd)) throw new Error('Reporting API returned an invalid response.')
      setTemplates(td)
      setRuns(rd)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load reporting data.')
    } finally {
      setLoading(false)
    }
  }, [headers])

  useEffect(() => { load() }, [load])

  async function openRun(run: Run) {
    try {
      const response = await fetch(`${api}/reports/${run.report_run_id}/result`, { headers })
      if (!response.ok) throw new Error('This report has not produced a result yet.')
      setSelected(await response.json())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to open report result.')
    }
  }

  async function runNow() {
    setBusy(true)
    setMessage('Creating Daily Operations run…')
    try {
      const mr = await fetch(`${api}/reports`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
      const made = await mr.json()
      if (!mr.ok || !made.report_run_id) throw new Error(made.message || made.detail || 'Unable to create report.')
      const dr = await fetch(`${api}/reports/${made.report_run_id}/run`, { method: 'POST', headers })
      const done = await dr.json()
      if (!dr.ok) throw new Error(done.message || done.detail || 'Report generation failed.')
      setMessage(`Run ${done.report_run_id}: ${done.status}.`)
      await load()
      await openRun(done)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to generate report.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <LoadingState label="Loading governed reports…" />

  return (
    <div className="min-h-full bg-[var(--color-bg)]">
      <PageHeader title="Reports" />
      <div className="mx-auto w-full max-w-7xl space-y-6 p-6 lg:p-8">
        {message && <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text-secondary)] shadow-[var(--shadow-xs)]" role="status">{message}</div>}

        <Card className="relative overflow-hidden">
          <span className="absolute inset-y-0 left-0 w-1 bg-[var(--color-accent)]" aria-hidden="true" />
          <div className="flex items-center justify-between gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-11 w-11 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"><FileChartColumn size={21} aria-hidden="true" /></div>
              <div><h2 className="text-base font-semibold text-[var(--color-text-primary)]">Daily Operations</h2><p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--color-text-secondary)]">PDF, XLSX, PPTX and DOCX from one governed result, including movements, cargo, delays, exceptions and provenance.</p></div>
            </div>
            <button disabled={busy} onClick={runNow} className="inline-flex min-h-10 flex-shrink-0 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"><Play size={14} fill="currentColor" aria-hidden="true" />{busy ? 'Generating…' : 'Run Now'}</button>
          </div>
        </Card>

        {selected && <Card><div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4"><div><h2 className="text-base font-semibold">Daily Operations result</h2><p className="mt-1 font-mono text-[11px] text-[var(--color-text-secondary)]">Run {selected.report_run_id}</p></div><div className="flex items-center gap-2"><StatusBadge status={selected.status} /><button onClick={() => setSelected(null)} aria-label="Close report result" className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)]"><X size={15} /></button></div></div><div className="grid gap-3 md:grid-cols-2">{Object.entries(selected.result.sections).map(([key, section]) => <details key={key} open className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3"><summary className="cursor-pointer text-sm font-semibold">{section.title}</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-[var(--color-text-secondary)]">{pretty(section.value)}</pre></details>)}</div><p className="mt-4 text-xs text-[var(--color-text-tertiary)]">Metadata and methodology are included in the governed result; values are not recomputed in the browser.</p></Card>}

        <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
          <Card padded={false} className="overflow-hidden"><div className="border-b border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-5 py-4"><h2 className="text-base font-semibold">Report history</h2><p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">Generated results and current execution state</p></div>{runs.length === 0 ? <EmptyState title="No report runs yet" description="Select Run Now to create the first Daily Operations report." /> : <div className="divide-y divide-[var(--color-border)]">{runs.map(run => <div key={run.report_run_id} className="flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-[var(--color-surface-subtle)]"><div className="min-w-0"><button onClick={() => openRun(run)} className="block max-w-full truncate font-mono text-xs font-semibold text-[var(--color-accent)] hover:underline">{run.report_run_id}</button><div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--color-text-secondary)]"><span>{run.template_id}</span><StatusBadge status={run.status} showGlyph={false} /><span>{run.progress}%</span></div>{run.failure_reason && <p className="mt-1 text-xs text-[var(--color-critical)]">{run.failure_reason}</p>}</div><div className="flex flex-wrap justify-end gap-1">{run.formats.map(format => <span key={format} className="rounded border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-text-secondary)]">{format}</span>)}</div></div>)}</div>}</Card>

          <div className="space-y-6"><Card><h2 className="text-base font-semibold mb-3">Template registry</h2><div className="space-y-3">{templates.map(t => <div key={t.template_id} className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] pb-3 last:border-0 last:pb-0"><div><p className="text-sm font-medium">{t.name}</p><p className="text-[11px] text-[var(--color-text-tertiary)]">Version {t.version} · {t.sections.length} sections</p></div><StatusBadge label={t.status === 'DEFERRED' ? 'Registered / deferred' : 'Implemented'} tone={t.status === 'DEFERRED' ? 'neutral' : 'good'} /></div>)}</div></Card><Card><div className="flex items-start gap-3"><CalendarClock size={18} className="mt-0.5 text-[var(--color-accent)]" /><div><h2 className="text-sm font-semibold">Schedule configuration</h2><p className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">Schedules are configured through the reporting API. A deployed scheduler invokes them; this application does not claim to run cron locally.</p><Link href="/copilot" className="mt-3 inline-block text-xs font-semibold text-[var(--color-accent)] hover:underline">Ask Copilot about report metrics →</Link></div></div></Card></div>
        </div>
      </div>
    </div>
  )
}
