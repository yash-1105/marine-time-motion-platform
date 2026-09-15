'use client'

import { useEffect, useState } from 'react'
import { Card, PageHeader } from '@/components/ui'
import { useAuth } from '@/lib/auth-context'

const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
type Template = { template_id: string; name: string; version: string; status: string; sections: string[] }

export default function ReportsPage() {
  const { token } = useAuth() as { token?: string }
  const [templates, setTemplates] = useState<Template[]>([]); const [message, setMessage] = useState('')
  useEffect(() => { fetch(`${api}/reports/templates`, { headers: { Authorization: `Bearer ${token || 'dev-token'}` } }).then(r => r.json()).then(setTemplates).catch(() => setMessage('Unable to load report templates.')) }, [token])
  async function runNow() {
    setMessage('Creating Daily Operations run…')
    const h = { 'Content-Type': 'application/json', Authorization: `Bearer ${token || 'dev-token'}` }
    const made = await fetch(`${api}/reports`, { method: 'POST', headers: h, body: JSON.stringify({}) }).then(r => r.json())
    if (!made.report_run_id) return setMessage(made.message || 'Unable to create report.')
    const done = await fetch(`${api}/reports/${made.report_run_id}/run`, { method: 'POST', headers: h }).then(r => r.json())
    setMessage(`Run ${done.report_run_id}: ${done.status}. It is available for approval once generated.`)
  }
  return <div className="p-6 space-y-5"><PageHeader title="Reports" description="Governed reports use the same analytics and dashboard results as the application." />
    <Card><div className="flex items-center justify-between gap-4"><div><h2 className="font-semibold">Daily Operations</h2><p className="text-sm text-[var(--color-text-secondary)]">PDF, XLSX, PPTX and DOCX from one governed result.</p></div><button onClick={runNow} className="px-3 py-2 rounded bg-[var(--color-accent)] text-white text-sm">Run Now</button></div>{message && <p className="mt-3 text-sm" role="status">{message}</p>}</Card>
    <Card><h2 className="font-semibold mb-3">Template registry</h2><div className="space-y-2">{templates.map(t => <div key={t.template_id} className="flex justify-between text-sm"><span>{t.name} · v{t.version}</span><span>{t.status === 'DEFERRED' ? 'Registered / deferred' : 'Implemented'}</span></div>)}</div></Card>
    <Card><h2 className="font-semibold">Schedule configuration</h2><p className="text-sm text-[var(--color-text-secondary)] mt-1">Schedules are configured through the reporting API. A deployed scheduler invokes them; this application does not claim to run cron locally.</p></Card>
  </div>
}
