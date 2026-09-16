'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Card, PageHeader, LoadingState } from '@/components/ui'
import { useAuth } from '@/lib/auth-context'

const api = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1'
type Template = { template_id: string; name: string; version: string; status: string; sections: string[] }
type Run = { report_run_id: string; status: string; progress: number; template_id: string; formats: string[]; failure_reason?: string | null; version: number }
type ReportResult = { report_run_id: string; status: string; result: { metadata: Record<string, unknown>; sections: Record<string, { title: string; value: unknown }> } }

function pretty(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) }

export default function ReportsPage() {
  const { token } = useAuth()
  const headers = useMemo(() => ({ Authorization: `Bearer ${token || 'dev-token'}` }), [token])
  const [templates, setTemplates] = useState<Template[]>([]); const [runs, setRuns] = useState<Run[]>([])
  const [selected, setSelected] = useState<ReportResult | null>(null); const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [tr, rr] = await Promise.all([fetch(`${api}/reports/templates`, { headers }), fetch(`${api}/reports/runs`, { headers })])
      if (!tr.ok || !rr.ok) throw new Error('Unable to load reporting data.')
      const [td, rd] = await Promise.all([tr.json(), rr.json()])
      if (!Array.isArray(td) || !Array.isArray(rd)) throw new Error('Reporting API returned an invalid response.')
      setTemplates(td); setRuns(rd)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to load reporting data.') }
    finally { setLoading(false) }
  }, [headers])
  useEffect(() => { load() }, [load])
  async function openRun(run: Run) {
    try { const response = await fetch(`${api}/reports/${run.report_run_id}/result`, { headers }); if (!response.ok) throw new Error('This report has not produced a result yet.'); setSelected(await response.json()) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to open report result.') }
  }
  async function runNow() {
    setBusy(true); setMessage('Creating Daily Operations run…')
    try {
      const mr = await fetch(`${api}/reports`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({}) }); const made = await mr.json()
      if (!mr.ok || !made.report_run_id) throw new Error(made.message || made.detail || 'Unable to create report.')
      const dr = await fetch(`${api}/reports/${made.report_run_id}/run`, { method: 'POST', headers }); const done = await dr.json()
      if (!dr.ok) throw new Error(done.message || done.detail || 'Report generation failed.')
      setMessage(`Run ${done.report_run_id}: ${done.status}.`); await load(); await openRun(done)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to generate report.') }
    finally { setBusy(false) }
  }
  if (loading) return <LoadingState label="Loading governed reports…" />
  return <div className="p-6 space-y-5">
    <PageHeader title="Reports" description="Governed reports use the same analytics and dashboard results as the application." />
    {message && <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm" role="status">{message}</div>}
    <Card><div className="flex items-center justify-between gap-4"><div><h2 className="font-semibold">Daily Operations</h2><p className="text-sm text-[var(--color-text-secondary)]">PDF, XLSX, PPTX and DOCX from one governed result, including movements, cargo, delays, exceptions and provenance.</p></div><button disabled={busy} onClick={runNow} className="px-3 py-2 rounded bg-[var(--color-accent)] text-white text-sm disabled:opacity-50">{busy ? 'Generating…' : 'Run Now'}</button></div></Card>
    {selected && <Card><div className="flex items-center justify-between mb-3"><div><h2 className="font-semibold">Daily Operations result</h2><p className="text-xs text-[var(--color-text-secondary)]">Run {selected.report_run_id} · {selected.status}</p></div><button onClick={() => setSelected(null)} className="text-xs underline">Close</button></div><div className="grid gap-3 md:grid-cols-2">{Object.entries(selected.result.sections).map(([key, section]) => <details key={key} open className="rounded-md border border-[var(--color-border)] p-3"><summary className="cursor-pointer text-sm font-semibold">{section.title}</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-[var(--color-text-secondary)]">{pretty(section.value)}</pre></details>)}</div><p className="mt-3 text-xs text-[var(--color-text-tertiary)]">Metadata and methodology are included in the governed result; values are not recomputed in the browser.</p></Card>}
    <Card><h2 className="font-semibold mb-3">Report history</h2>{runs.length === 0 ? <p className="text-sm text-[var(--color-text-secondary)]">No report runs yet. Select Run Now to create one.</p> : <div className="divide-y divide-[var(--color-border)]">{runs.map(run => <div key={run.report_run_id} className="flex items-center justify-between gap-3 py-3 text-sm"><div><button onClick={() => openRun(run)} className="font-medium text-[var(--color-accent)] underline">{run.report_run_id}</button><span className="ml-3 text-xs text-[var(--color-text-secondary)]">{run.template_id} · {run.status} · {run.progress}%</span>{run.failure_reason && <p className="text-xs text-[var(--color-critical)]">{run.failure_reason}</p>}</div><span className="text-xs text-[var(--color-text-tertiary)]">{run.formats.join(', ')}</span></div>)}</div>}</Card>
    <Card><h2 className="font-semibold mb-3">Template registry</h2><div className="space-y-2">{templates.map(t => <div key={t.template_id} className="flex justify-between text-sm"><span>{t.name} · v{t.version}</span><span>{t.status === 'DEFERRED' ? 'Registered / deferred' : 'Implemented'}</span></div>)}</div></Card>
    <Card><h2 className="font-semibold">Schedule configuration</h2><p className="text-sm text-[var(--color-text-secondary)] mt-1">Schedules are configured through the reporting API. A deployed scheduler invokes them; this application does not claim to run cron locally.</p><Link href="/copilot" className="mt-3 inline-block text-xs text-[var(--color-accent)] underline">Ask Copilot about governed report metrics →</Link></Card>
  </div>
}
