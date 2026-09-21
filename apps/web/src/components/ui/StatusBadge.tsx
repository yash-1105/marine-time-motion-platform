'use client'

import React from 'react'
import { CircleCheck, CircleMinus, CircleX, Sparkles, TriangleAlert, type LucideIcon } from 'lucide-react'

export type StatusTone = 'good' | 'warning' | 'critical' | 'inferred' | 'neutral'

const TONE_STYLES: Record<StatusTone, string> = {
  good: 'text-[var(--color-good)] bg-[var(--color-good-bg)] border-[var(--color-good-border)]',
  warning: 'text-[var(--color-warning)] bg-[var(--color-warning-bg)] border-[var(--color-warning-border)]',
  critical: 'text-[var(--color-critical)] bg-[var(--color-critical-bg)] border-[var(--color-critical-border)]',
  inferred: 'text-[var(--color-inferred)] bg-[var(--color-inferred-bg)] border-[var(--color-inferred-border)]',
  neutral: 'text-[var(--color-neutral)] bg-[var(--color-neutral-bg)] border-[var(--color-neutral-border)]',
}

const TONE_GLYPH: Record<StatusTone, LucideIcon> = {
  good: CircleCheck,
  warning: TriangleAlert,
  critical: CircleX,
  inferred: Sparkles,
  neutral: CircleMinus,
}

/**
 * Maps common backend status/band vocabulary to a visual tone.
 * Falls back to 'neutral' for anything unrecognized (e.g. NO_SOURCE_DATA, UNAVAILABLE)
 * so unknown/ungoverned states never silently render as "good".
 */
export function statusToTone(status: string | null | undefined): StatusTone {
  const s = (status || '').toUpperCase()
  if (['GOOD', 'GREEN', 'CLEAN', 'PASS', 'ON_TARGET', 'HEALTHY', 'COMPUTED', 'CONFIRMED', 'ACTIVE', 'READY', 'AVAILABLE', 'RESOLVED', 'MERGED', 'RECONCILED'].includes(s)) {
    return 'good'
  }
  if (['WARNING', 'AMBER', 'FLAGGED', 'WATCH', 'MEDIUM', 'HOLD', 'PASSIVE_WAIT', 'UNCLASSIFIED', 'PENDING', 'DELAYED', 'AT_RISK'].includes(s)) {
    return 'warning'
  }
  if (['CRITICAL', 'RED', 'QUARANTINED', 'FAIL', 'FAILED', 'ERROR', 'HIGH', 'OFF_TARGET', 'OVERDUE', 'STALE', 'BLOCKED_CONFLICT', 'SEQUENCE_VIOLATION'].includes(s)) {
    return 'critical'
  }
  if (['INFERRED', 'ESTIMATED', 'AI_INFERRED'].includes(s)) {
    return 'inferred'
  }
  return 'neutral'
}

export interface StatusBadgeProps {
  /** Raw backend status/band string, e.g. "QUARANTINED", "NO_SOURCE_DATA". Humanized for display unless `label` is given. */
  status?: string
  /** Explicit display label; overrides the humanized `status` text. */
  label?: string
  /** Explicit tone; overrides the tone auto-derived from `status` via statusToTone(). */
  tone?: StatusTone
  showGlyph?: boolean
  className?: string
}

function humanize(status: string): string {
  return status
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Status is never carried by colour alone: every badge pairs colour with a glyph and a text label. */
export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  tone,
  showGlyph = true,
  className = '',
}) => {
  const resolvedTone = tone ?? statusToTone(status)
  const resolvedLabel = label ?? (status ? humanize(status) : '')
  const Glyph = TONE_GLYPH[resolvedTone]

  return (
    <span
      className={`inline-flex min-h-6 items-center gap-1.5 px-2 py-0.5 rounded-md border text-[11px] leading-4 font-semibold whitespace-nowrap ${TONE_STYLES[resolvedTone]} ${className}`}
    >
      {showGlyph && <Glyph size={12} strokeWidth={2} aria-hidden="true" />}
      {resolvedLabel}
    </span>
  )
}
