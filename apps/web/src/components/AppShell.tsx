'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '../lib/auth-context'
import { useDatasetStatus } from '../lib/dataset-context'
import { GlobalFilterBar } from './GlobalFilterBar'
import { EmptyState, LoadingState, ErrorState } from './ui'

// Pages whose data is actually driven by the global Scope filter bar.
// Other pages either use their own local filters or are record/detail-specific,
// so showing the bar there would be inert noise.
const SCOPE_FILTER_PATHS = new Set(['/', '/vessel-calls', '/time-and-motion'])

interface NavItem {
  label: string
  path: string
  requiredAction: string
  glyph: string
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const ALL_ROLES = [
  'Platform Administrator',
  'Data Steward',
  'Marine Operations Controller',
  'Analyst',
  'Department Head',
  'Executive',
  'Report Manager',
  'Auditor',
  'Integration Service Account',
]

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Overview',
    items: [{ label: 'Executive Dashboard', path: '/', requiredAction: 'view', glyph: '▦' }],
  },
  {
    label: 'Operations',
    items: [
      { label: 'Vessel Calls', path: '/vessel-calls', requiredAction: 'view', glyph: '⚓' },
      { label: 'Vessel Journey', path: '/vessel-journey', requiredAction: 'view', glyph: '⇄' },
      { label: 'Data Ingestion', path: '/ingestion', requiredAction: 'view', glyph: '⤓' },
    ],
  },
  {
    label: 'Analytics',
    items: [
      { label: 'Time & Motion Explorer', path: '/time-and-motion', requiredAction: 'view', glyph: '◰' },
      { label: 'Governed KPIs', path: '/kpis', requiredAction: 'view', glyph: '◎' },
      { label: 'Delays & Bottlenecks', path: '/delays', requiredAction: 'view', glyph: '⏳' },
    ],
  },
  {
    label: 'Data Governance',
    items: [
      { label: 'Data Quality', path: '/data-quality', requiredAction: 'view', glyph: '✔' },
      { label: 'Identity & Merges', path: '/identity', requiredAction: 'view', glyph: '⧉' },
    ],
  },
]

const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items)

const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  ALL_NAV_ITEMS.map((item) => [item.path, item.label])
)

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname()
  const { user, roles, permissions, can, switchRole, logout } = useAuth()
  const { status: datasetStatus, errorMessage: datasetError, refresh: refreshDataset } = useDatasetStatus()

  const currentRole = roles[0] || 'Platform Administrator'
  const currentTitle = PAGE_TITLES[pathname] || 'Marine Time & Motion'
  const showScopeFilter = SCOPE_FILTER_PATHS.has(pathname)
  const isIngestionPage = pathname === '/ingestion'
  const showDatasetGate = !isIngestionPage && datasetStatus !== 'ready' && datasetStatus !== 'loading'

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      {/* Sidebar */}
      <aside className="w-64 bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col flex-shrink-0">
        <div className="h-14 px-4 flex items-center gap-2 border-b border-[var(--color-border)]">
          <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] inline-block" aria-hidden="true" />
          <span className="font-semibold text-sm tracking-tight text-[var(--color-text-primary)]">
            Marine Time &amp; Motion
          </span>
        </div>

        <nav className="flex-1 py-3 overflow-y-auto" aria-label="Primary Navigation">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter((item) => can(item.requiredAction))
            if (visibleItems.length === 0) return null
            return (
              <div key={group.label} className="mb-4 px-3">
                <div className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-tertiary)]">
                  {group.label}
                </div>
                <ul className="space-y-0.5">
                  {visibleItems.map((item) => {
                    const isActive = pathname === item.path
                    return (
                      <li key={item.path}>
                        <Link
                          href={item.path}
                          aria-current={isActive ? 'page' : undefined}
                          className={`flex items-center gap-2.5 px-2.5 py-1.5 text-sm rounded-md transition-colors ${
                            isActive
                              ? 'bg-[var(--color-accent-soft)] text-[var(--color-accent)] font-medium'
                              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text-primary)]'
                          }`}
                        >
                          <span className="text-sm w-4 text-center flex-shrink-0" aria-hidden="true">
                            {item.glyph}
                          </span>
                          <span className="truncate">{item.label}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </nav>

        <div className="p-3 border-t border-[var(--color-border)]">
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="role-select" className="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-semibold">
              Role
            </label>
            <button
              onClick={() => logout()}
              className="text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] cursor-pointer"
            >
              Sign out
            </button>
          </div>
          <select
            id="role-select"
            aria-label="Switch Role"
            value={currentRole}
            onChange={(e) => switchRole(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md px-2 py-1.5 text-xs text-[var(--color-text-primary)] font-medium focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] cursor-pointer"
          >
            {ALL_ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <div className="text-[11px] text-[var(--color-text-tertiary)] truncate mt-1.5">
            {user?.email || 'admin@port.local'} &middot; {permissions.length} actions
          </div>
        </div>
      </aside>

      {/* Main workspace */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <header className="h-14 flex-shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)]">
          <h1 className="text-sm font-semibold text-[var(--color-text-primary)]">{currentTitle}</h1>
        </header>

        {showScopeFilter && !showDatasetGate && (
          <React.Suspense fallback={<div className="h-12 bg-[var(--color-surface)] border-b border-[var(--color-border)]" />}>
            <GlobalFilterBar />
          </React.Suspense>
        )}

        <main className="flex-1 overflow-y-auto min-w-0 flex flex-col">
          {showDatasetGate ? (
            <div className="flex-1 flex items-center justify-center p-8">
              {datasetStatus === 'processing' ? (
                <LoadingState label="Processing dataset…" />
              ) : datasetStatus === 'failed' ? (
                <ErrorState
                  title="Dataset processing failed"
                  description={datasetError}
                  onRetry={refreshDataset}
                />
              ) : (
                <EmptyState
                  title="No dataset loaded"
                  description="Upload a vessel operations dataset to view operational analytics."
                  action={
                    <Link
                      href="/ingestion"
                      className="inline-flex items-center px-4 py-1.5 bg-[var(--color-accent)] hover:opacity-90 text-white rounded-md text-sm font-medium"
                    >
                      Upload Dataset
                    </Link>
                  }
                />
              )}
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  )
}
