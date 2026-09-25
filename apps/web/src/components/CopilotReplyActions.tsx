'use client'

import { Fragment, useState } from 'react'
import { ExternalLink, FileSearch, X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export type CopilotEvidenceContext = {
  source?: string
  method?: string
  dataset_id?: string
  vcn?: string
  vessel_name?: string
  metric?: string
  service?: string
  rule_id?: string
  observed_value?: unknown
  threshold?: unknown
  reason?: string
  journey_leg?: string
  source_record_ids?: string[]
  related_paths?: string[]
}

export type CopilotActionReply = {
  analysis_path?: string | null
  evidence?: string[]
  evidence_context?: CopilotEvidenceContext
}

function safePath(value?: string | null): string | null {
  return value && value.startsWith('/') ? value : null
}

function readableValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Unavailable'
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'Unavailable'
  return String(value)
}

const labels: Array<[keyof CopilotEvidenceContext, string]> = [
  ['source', 'Source'],
  ['method', 'Method'],
  ['dataset_id', 'Dataset / ingestion run'],
  ['vcn', 'Vessel / VCN'],
  ['vessel_name', 'Vessel name'],
  ['metric', 'Metric'],
  ['service', 'Service'],
  ['rule_id', 'Rule'],
  ['observed_value', 'Observed value'],
  ['threshold', 'Threshold / benchmark'],
  ['reason', 'Reason'],
  ['journey_leg', 'Journey leg'],
]

/**
 * Explicit Copilot actions for a server-authorized governed result.  Evidence is
 * displayed in-app rather than being represented by an opaque URL named “Open”.
 */
export function CopilotReplyActions({ reply, onNavigate }: { reply: CopilotActionReply; onNavigate?: () => void }) {
  const router = useRouter()
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const analysisPath = safePath(reply.analysis_path)
  const context = reply.evidence_context || {}
  const relatedPaths = [...new Set([...(reply.evidence || []), ...(context.related_paths || [])])]
    .map(safePath)
    .filter((path): path is string => Boolean(path))
  const hasEvidence = relatedPaths.length > 0 || Boolean(context.source_record_ids?.length || context.dataset_id || context.rule_id)

  const openAnalysis = () => {
    if (!analysisPath) return
    // Start the App Router transition while this client component is still mounted.
    // Closing the floating panel first unmounts this component and cancels the push.
    router.push(analysisPath)
    onNavigate?.()
  }

  return (
    <>
      {(analysisPath || hasEvidence) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {analysisPath && (
            <button
              type="button"
              onClick={openAnalysis}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--color-accent)] px-2.5 py-1.5 text-[10px] font-semibold text-white transition-colors hover:bg-[var(--color-accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
            >
              View analysis <ExternalLink size={11} aria-hidden="true" />
            </button>
          )}
          {hasEvidence && (
            <button
              type="button"
              onClick={() => setEvidenceOpen(true)}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-[10px] font-semibold text-[var(--color-accent)] transition-colors hover:border-[var(--color-accent-soft-border)] hover:bg-[var(--color-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Evidence: Open <FileSearch size={11} aria-hidden="true" />
            </button>
          )}
        </div>
      )}

      {evidenceOpen && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/35 p-4" role="presentation">
          <section
            aria-modal="true"
            aria-labelledby="copilot-evidence-title"
            role="dialog"
            className="max-h-[min(680px,calc(100vh-2rem))] w-full max-w-xl overflow-y-auto rounded-[var(--radius-lg)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)]"
          >
            <header className="flex items-start justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4">
              <div>
                <h2 id="copilot-evidence-title" className="text-sm font-semibold text-[var(--color-text-primary)]">Governed evidence</h2>
                <p className="mt-1 text-xs text-[var(--color-text-secondary)]">This evidence was returned by the tenant-scoped source used for this answer.</p>
              </div>
              <button type="button" onClick={() => setEvidenceOpen(false)} aria-label="Close evidence" className="rounded-md p-1 text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text-primary)]">
                <X size={17} aria-hidden="true" />
              </button>
            </header>
            <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-4 gap-y-3 px-5 py-4 text-xs">
              {labels.map(([key, label]) => context[key] !== undefined && context[key] !== '' && (
                <Fragment key={String(key)}>
                  <dt className="font-medium text-[var(--color-text-secondary)]">{label}</dt>
                  <dd className="break-words text-[var(--color-text-primary)]">{readableValue(context[key])}</dd>
                </Fragment>
              ))}
              {context.source_record_ids && context.source_record_ids.length > 0 && (
                <Fragment>
                  <dt className="font-medium text-[var(--color-text-secondary)]">Source record IDs</dt>
                  <dd className="break-all font-mono text-[10px] leading-5 text-[var(--color-text-primary)]">{context.source_record_ids.join(', ')}</dd>
                </Fragment>
              )}
            </dl>
            {relatedPaths.length > 0 && (
              <footer className="border-t border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-5 py-3">
                <p className="mb-2 text-[11px] font-semibold text-[var(--color-text-secondary)]">Related governed analysis</p>
                <div className="flex flex-wrap gap-2">
                  {relatedPaths.map((path) => <Link key={path} href={path} onClick={() => { setEvidenceOpen(false); onNavigate?.() }} className="inline-flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline">Open source <ExternalLink size={10} aria-hidden="true" /></Link>)}
                </div>
              </footer>
            )}
          </section>
        </div>
      )}
    </>
  )
}
