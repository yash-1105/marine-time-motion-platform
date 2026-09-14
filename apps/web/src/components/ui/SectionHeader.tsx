'use client'

import React from 'react'

export interface SectionHeaderProps {
  title: string
  description?: string
  /** Right-aligned slot — typically a "View all" link or a small control. */
  action?: React.ReactNode
  className?: string
}

/** Small section-level heading used inside a page body, above a Card or group of Cards. */
export const SectionHeader: React.FC<SectionHeaderProps> = ({ title, description, action, className = '' }) => (
  <div className={`flex items-start justify-between gap-3 mb-3 ${className}`}>
    <div>
      <h2 className="text-base font-semibold text-[var(--color-text-primary)]">{title}</h2>
      {description && <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{description}</p>}
    </div>
    {action && <div className="flex-shrink-0 text-sm">{action}</div>}
  </div>
)
