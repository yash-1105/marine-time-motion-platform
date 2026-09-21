'use client'

import React from 'react'

export interface PageHeaderProps {
  title: string
  /** Compact route metadata — e.g. data provenance, status, or last-updated details. */
  meta?: React.ReactNode
  /** Right-aligned slot — buttons, export links, etc. Rendered next to the title row. */
  actions?: React.ReactNode
  className?: string
}

/**
 * Compact route toolbar. The application shell owns the single primary page
 * heading; this component only preserves useful route metadata and actions.
 */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, meta, actions, className = '' }) => {
  if (!meta && !actions) return null

  return (
    <section
      aria-label={`${title} controls`}
      className={`min-h-12 px-6 lg:px-8 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex flex-wrap items-center justify-between gap-3 flex-shrink-0 ${className}`}
    >
      {meta ? <div className="min-w-0 text-xs text-[var(--color-text-secondary)]">{meta}</div> : <span />}
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </section>
  )
}
