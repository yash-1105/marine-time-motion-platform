'use client'

import React from 'react'
import Link from 'next/link'
import { Card } from './Card'
import { StatusBadge, type StatusTone } from './StatusBadge'

export interface KpiCardProps {
  label: string
  /** The headline number. Pass a string like "UNAVAILABLE" or "NO_SOURCE_DATA" rather than 0 for uncomputed metrics. */
  value: React.ReactNode
  unit?: string
  /** e.g. "n = 128 calls" */
  sampleSize?: string
  /** e.g. "Target: < 24h" */
  target?: React.ReactNode
  /** e.g. "+3.2h vs target" */
  variance?: React.ReactNode
  /** Raw backend status/band string (e.g. "ON_TARGET", "NO_SOURCE_DATA") — mapped to a tone automatically. */
  status?: string
  /** Explicit tone override, takes precedence over `status`. */
  tone?: StatusTone
  /** Free-form supporting context rendered under the value. */
  context?: React.ReactNode
  /** Optional drill-through destination — every KPI should trace to evidence. */
  href?: string
  className?: string
}

/** Large, scannable metric card. One KPI per card — the number must be the most prominent thing on it. */
export const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  unit,
  sampleSize,
  target,
  variance,
  status,
  tone,
  context,
  href,
  className = '',
}) => {
  const body = (
    <Card className={`h-full ${href ? 'transition-shadow hover:shadow-[0_2px_8px_rgba(15,23,42,0.08)]' : ''} ${className}`}>
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-secondary)]">
          {label}
        </span>
        {status && <StatusBadge status={status} tone={tone} showGlyph={false} />}
      </div>

      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-semibold tabular-nums text-[var(--color-text-primary)]">{value}</span>
        {unit && <span className="text-sm text-[var(--color-text-secondary)]">{unit}</span>}
      </div>

      {(sampleSize || target || variance || context) && (
        <div className="mt-2 text-xs text-[var(--color-text-tertiary)] flex items-center gap-2 flex-wrap">
          {sampleSize && <span>{sampleSize}</span>}
          {target && <span>{target}</span>}
          {variance && <span>{variance}</span>}
          {context}
        </div>
      )}
    </Card>
  )

  if (href) {
    return (
      <Link href={href} className="block focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] rounded-lg">
        {body}
      </Link>
    )
  }

  return body
}
