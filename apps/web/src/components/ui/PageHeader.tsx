'use client'

import React from 'react'

export interface PageHeaderProps {
  title: string
  description?: string
  /** Small secondary line under the description — e.g. data-provenance or last-updated metadata. */
  meta?: React.ReactNode
  /** Right-aligned slot — buttons, export links, etc. Rendered next to the title row. */
  actions?: React.ReactNode
  className?: string
}

/** Standard page-level header: large title, one-line description, optional meta + actions. */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, description, meta, actions, className = '' }) => (
  <div className={`px-6 pt-6 pb-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex-shrink-0 ${className}`}>
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-text-primary)]">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-[var(--color-text-secondary)] max-w-2xl">{description}</p>
        )}
        {meta && <div className="mt-2 text-xs text-[var(--color-text-tertiary)]">{meta}</div>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  </div>
)
