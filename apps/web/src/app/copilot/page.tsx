'use client'

import { FormEvent, useState } from 'react'
import { ExternalLink, Send, Sparkles } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Card, EmptyState, PageHeader, StatusBadge } from '@/components/ui'

const api = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1'

type Reply = {
  answer: string
  conversation_id: string
  tool: string
  evidence: string[]
  result: unknown
  method: string
  data_quality_caveat: string
  suggested_action: string
}

export default function CopilotPage() {
  const { token } = useAuth()
  const [q, setQ] = useState('')
  const [items, setItems] = useState<Reply[]>([])
  const [busy, setBusy] = useState(false)
  const [cid, setCid] = useState<string>()

  async function send(e: FormEvent) {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    try {
      const r = await fetch(`${api}/copilot/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token || 'dev-token'}` },
        body: JSON.stringify({ question: q, conversation_id: cid }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.message || 'Copilot request failed')
      setCid(d.conversation_id)
      setItems((x) => [...x, d])
      setQ('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-[var(--color-bg)]">
      <PageHeader title="Copilot" description="Ask questions across governed operational data. Responses remain access-scoped, reproducible, and linked to evidence." meta={<StatusBadge label="Governed tool access" tone="good" />} />
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col p-6 lg:p-8">
        <Card padded={false} className="flex min-h-[560px] flex-1 flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-5 py-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"><Sparkles size={17} aria-hidden="true" /></div>
            <div><h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Operational intelligence workspace</h2><p className="text-[11px] text-[var(--color-text-secondary)]">Source data is treated as evidence, never as instructions.</p></div>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto bg-[var(--color-surface-subtle)] p-5">
            {items.length === 0 ? <EmptyState icon={<Sparkles size={20} />} title="Start with an operational question" description="Ask about lead times, delays, KPIs, vessel journeys, cohorts, or governed trends." /> : items.map((r, i) => (
              <article key={i} className="max-w-3xl rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-xs)]">
                <p className="text-sm font-medium leading-6 text-[var(--color-text-primary)]">{r.answer}</p>
                <div className="mt-3 flex flex-wrap gap-2"><StatusBadge label={r.tool} tone="neutral" showGlyph={false} /><StatusBadge label={r.method} tone="inferred" showGlyph={false} /></div>
                <p className="mt-3 border-l-2 border-[var(--color-warning-border)] pl-3 text-xs leading-5 text-[var(--color-text-secondary)]">{r.data_quality_caveat}</p>
                {r.evidence.length > 0 && <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-secondary)]"><span className="font-semibold">Evidence</span>{r.evidence.map((x) => <a className="inline-flex items-center gap-1 text-[var(--color-accent)] hover:underline" href={x} key={x}>Open source <ExternalLink size={10} /></a>)}</div>}
                <details className="mt-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-subtle)] p-3"><summary className="cursor-pointer text-xs font-semibold text-[var(--color-text-secondary)]">Governed result</summary><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-[11px] leading-5 text-[var(--color-text-secondary)]">{JSON.stringify(r.result, null, 2)}</pre></details>
              </article>
            ))}
          </div>
          <form onSubmit={send} className="flex gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <input value={q} onChange={(e) => setQ(e.target.value)} className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3.5 py-2.5 text-sm outline-none focus:border-[var(--color-accent)]" aria-label="Ask Copilot" placeholder="Ask about governed operations data…" />
            <button disabled={busy || !q.trim()} className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"><Send size={15} aria-hidden="true" /> {busy ? 'Using governed tools…' : 'Send'}</button>
          </form>
        </Card>
      </div>
    </div>
  )
}
