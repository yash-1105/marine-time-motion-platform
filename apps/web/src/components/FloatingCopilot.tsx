'use client'

import { FormEvent, useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'
import { ExternalLink, Send, Sparkles, X } from 'lucide-react'
import { BrandMark } from './BrandMark'

const API = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1'

type CopilotReply = {
  answer: string
  conversation_id: string
  tool: string
  source_label?: string
  analysis_path?: string | null
  method: string
  data_quality_caveat: string
  evidence: string[]
  result: { status?: string; reason?: string; [key: string]: unknown }
}

type ChatItem = { question: string; reply?: CopilotReply; error?: string }

const STORAGE_KEY = 'marine-copilot-chat'

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
          className="flex h-[min(620px,calc(100vh-7rem))] w-[min(410px,calc(100vw-2rem))] flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)]"
        >
          <header className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3.5">
            <div className="flex items-center gap-3">
              <BrandMark className="h-8 w-8" />
              <div>
                <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Copilot</h2>
                <p className="text-[11px] text-[var(--color-text-secondary)]">Governed intelligence · access scoped</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close Copilot" className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text-primary)]"><X size={17} aria-hidden="true" /></button>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto bg-[var(--color-surface-subtle)] p-4 text-xs">
            {messages.length === 0 && (
              <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-[var(--color-text-secondary)] shadow-[var(--shadow-xs)]">
                <div className="mb-2 flex items-center gap-2 font-semibold text-[var(--color-text-primary)]"><Sparkles size={14} className="text-[var(--color-accent)]" /> Governed operational assistant</div>
                <p className="leading-5">Ask about outliers, data quality, delays, statistics, KPIs, vessel journeys, or uploaded files. Every answer is grounded in the matching governed source.</p>
              </div>
            )}
            {messages.map((item, index) => (
              <div key={`${item.question}-${index}`} className="space-y-2">
                <div className="ml-8 rounded-[var(--radius-lg)] rounded-br-sm border border-[var(--color-accent-soft-border)] bg-[var(--color-accent-soft)] px-3.5 py-2.5 leading-5 text-[var(--color-text-primary)]">{item.question}</div>
                {item.error ? (
                  <div role="alert" className="rounded-lg border border-[var(--color-critical-border)] bg-[var(--color-critical-bg)] px-3 py-2 text-[var(--color-critical)]">{item.error}</div>
                ) : item.reply ? (
                  <div className="mr-5 rounded-[var(--radius-lg)] rounded-tl-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-[var(--color-text-primary)] shadow-[var(--shadow-xs)]">
                    <p className="whitespace-pre-wrap leading-5">{item.reply.answer}</p>
                    <p className="mt-2 text-[10px] text-[var(--color-text-tertiary)]">Source: {item.reply.source_label || item.reply.tool} · {item.reply.method}</p>
                    {item.reply.data_quality_caveat && <p className="mt-1 text-[10px] text-[var(--color-text-secondary)]">{item.reply.data_quality_caveat}</p>}
                    {item.reply.result?.status === 'UNAVAILABLE' && <p className="mt-1 font-medium text-[var(--color-warning)]">UNAVAILABLE: {item.reply.result.reason || 'Required data is not available.'}</p>}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      {item.reply.analysis_path && <Link href={item.reply.analysis_path} className="inline-flex items-center gap-1 rounded-md bg-[var(--color-accent)] px-2.5 py-1.5 text-[10px] font-semibold text-white hover:bg-[var(--color-accent-hover)]">View analysis <ExternalLink size={11} /></Link>}
                      {item.reply.evidence.length > 0 && <span className="flex items-center gap-2 text-[10px] text-[var(--color-text-tertiary)]">Evidence: {item.reply.evidence.slice(0, 4).map((href) => <Link key={href} href={href} className="inline-flex items-center gap-0.5 font-medium text-[var(--color-accent)] hover:underline">Open <ExternalLink size={9} /></Link>)}</span>}
                    </div>
                  </div>
                ) : (
                  <div className="px-3 py-2 text-[var(--color-text-tertiary)]">Using governed tools…</div>
                )}
              </div>
            ))}
            {busy && <div className="text-[var(--color-text-tertiary)]" role="status">Copilot is checking governed data…</div>}
          </div>

          <form onSubmit={send} className="flex gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
            <input value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Ask Copilot" placeholder="Ask a governed question…" className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 py-2 text-xs text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]" />
            <button type="submit" disabled={busy || !question.trim()} className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--color-accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"><Send size={13} /> Send</button>
          </form>
        </section>
      )}
      <button onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label={open ? 'Close Copilot assistant' : 'Open Copilot assistant'} className="flex h-12 w-12 items-center justify-center rounded-full border border-[var(--color-accent-strong)] bg-[var(--color-accent)] text-white shadow-[0_7px_20px_rgba(7,92,87,0.25)] hover:-translate-y-0.5 hover:bg-[var(--color-accent-hover)]">{open ? <X size={20} aria-hidden="true" /> : <Sparkles size={19} aria-hidden="true" />}</button>
    </div>
  )
}
