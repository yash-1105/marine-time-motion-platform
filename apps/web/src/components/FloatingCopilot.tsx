'use client'

import { FormEvent, useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'

const API = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1'

type CopilotReply = {
  answer: string
  conversation_id: string
  tool: string
  method: string
  data_quality_caveat: string
  evidence: string[]
  result: { status?: string; reason?: string; [key: string]: unknown }
}

type ChatItem = { question: string; reply?: CopilotReply; error?: string }

const STORAGE_KEY = 'marine-copilot-chat'

function describeResult(reply: CopilotReply): string | null {
  if (reply.result?.status !== 'AVAILABLE') return null
  const summary = reply.result.summary as Record<string, unknown> | undefined
  if (!summary) return null
  const categories = Array.isArray(summary.top_categories) ? summary.top_categories as Array<Record<string, unknown>> : []
  const bottlenecks = Array.isArray(summary.top_bottlenecks) ? summary.top_bottlenecks as Array<Record<string, unknown>> : []
  const totalHours = typeof summary.total_delay_hours === 'number' ? summary.total_delay_hours : null
  const totalCount = typeof summary.total_delays_count === 'number' ? summary.total_delays_count : null
  const parts: string[] = []
  if (totalCount !== null && totalHours !== null) {
    parts.push(`${totalCount} confirmed delays account for ${totalHours.toFixed(1)} hours in the governed population.`)
  }
  if (categories.length) {
    const top = categories.slice(0, 3).map((item) => `${String(item.category)} (${String(item.count)} delays, ${String(item.percentage)}%)`)
    parts.push(`The most frequent categories are ${top.join(', ')}.`)
  }
  if (bottlenecks.length) {
    const names = bottlenecks.slice(0, 3).map((item) => String(item.stage_or_resource)).filter(Boolean)
    if (names.length) parts.push(`Highest-ranked bottleneck stages/resources: ${names.join(', ')}.`)
  }
  return parts.length ? parts.join(' ') : null
}

export function FloatingCopilot() {
  const { user, token } = useAuth()
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [conversationId, setConversationId] = useState<string>()
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
      if (saved.conversationId) setConversationId(saved.conversationId)
      if (Array.isArray(saved.messages)) setMessages(saved.messages.slice(-8))
    } catch {
      // A corrupt local chat history must never prevent the application loading.
    }
  }, [])

  useEffect(() => {
    if (messages.length || conversationId) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, messages: messages.slice(-8) }))
    }
  }, [messages, conversationId])

  if (!user) return null

  async function send(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    setQuestion('')
    setBusy(true)
    setMessages((items) => [...items, { question: text }])
    try {
      const response = await fetch(`${API}/copilot/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: text, conversation_id: conversationId }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.message || payload.detail || `Copilot request failed (${response.status})`)
      setConversationId(payload.conversation_id)
      setMessages((items) => {
        const next = [...items]
        next[next.length - 1] = { question: text, reply: payload }
        return next
      })
    } catch (error) {
      setMessages((items) => {
        const next = [...items]
        next[next.length - 1] = { question: text, error: error instanceof Error ? error.message : 'Unable to reach Copilot' }
        return next
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3">
      {open && (
        <section
          aria-label="Copilot assistant"
          className="flex h-[min(600px,calc(100vh-7rem))] w-[min(390px,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-2xl"
        >
          <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-accent)] px-4 py-3 text-white">
            <div>
              <h2 className="text-sm font-semibold">Copilot</h2>
              <p className="text-[11px] text-white/80">Governed answers, scoped to your access</p>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close Copilot" className="rounded p-1 text-lg leading-none hover:bg-white/15">×</button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-3 text-xs">
            {messages.length === 0 && (
              <div className="rounded-lg bg-[var(--color-surface-muted)] p-3 text-[var(--color-text-secondary)]">
                Ask about delays, lead times, KPIs, vessel journeys, or trends. Every answer is grounded in governed data.
              </div>
            )}
            {messages.map((item, index) => (
              <div key={`${item.question}-${index}`} className="space-y-2">
                <div className="rounded-lg bg-[var(--color-accent-soft)] px-3 py-2 text-[var(--color-text-primary)]">{item.question}</div>
                {item.error ? (
                  <div role="alert" className="rounded-lg border border-[var(--color-critical-border)] bg-[var(--color-critical-bg)] px-3 py-2 text-[var(--color-critical)]">{item.error}</div>
                ) : item.reply ? (
                  <div className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-[var(--color-text-primary)]">
                    <p className="whitespace-pre-wrap">{item.reply.answer}</p>
                    {describeResult(item.reply) && <p className="mt-2 leading-relaxed text-[var(--color-text-primary)]">{describeResult(item.reply)}</p>}
                    <p className="mt-2 text-[10px] text-[var(--color-text-tertiary)]">Tool: {item.reply.tool} · {item.reply.method}</p>
                    <p className="mt-1 text-[10px] text-[var(--color-text-secondary)]">{item.reply.data_quality_caveat}</p>
                    {item.reply.result?.status === 'UNAVAILABLE' && <p className="mt-1 font-medium text-[var(--color-warning)]">UNAVAILABLE: {item.reply.result.reason || 'Required data is not available.'}</p>}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      {(item.reply.tool === 'delay_analysis' || item.reply.tool === 'cohort_statistics') && <Link href="/delays" className="rounded-md bg-[var(--color-accent)] px-2.5 py-1.5 text-[10px] font-medium text-white hover:opacity-90">View delays &amp; bottlenecks →</Link>}
                      {item.reply.evidence.length > 0 && <span className="flex items-center gap-2 text-[10px] text-[var(--color-text-tertiary)]">Evidence: {item.reply.evidence.slice(0, 4).map((href) => <Link key={href} href={href} className="text-[var(--color-accent)] underline">Open</Link>)}</span>}
                    </div>
                  </div>
                ) : (
                  <div className="px-3 py-2 text-[var(--color-text-tertiary)]">Using governed tools…</div>
                )}
              </div>
            ))}
            {busy && <div className="text-[var(--color-text-tertiary)]" role="status">Copilot is checking governed data…</div>}
          </div>

          <form onSubmit={send} className="flex gap-2 border-t border-[var(--color-border)] p-3">
            <input value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Ask Copilot" placeholder="Ask a question…" className="min-w-0 flex-1 rounded-md border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2 text-xs text-[var(--color-text-primary)] outline-none focus:ring-2 focus:ring-[var(--color-accent)]" />
            <button type="submit" disabled={busy || !question.trim()} className="rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">Send</button>
          </form>
        </section>
      )}
      <button onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label={open ? 'Close Copilot assistant' : 'Open Copilot assistant'} className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--color-accent)] text-2xl text-white shadow-lg transition-transform hover:scale-105 focus:outline-none focus:ring-4 focus:ring-[var(--color-accent-soft-border)]">{open ? '×' : '✦'}</button>
    </div>
  )
}
