'use client'

import React, { useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '../lib/auth-context'
import { useDatasetStatus } from '../lib/dataset-context'
import { GlobalFilterBar } from './GlobalFilterBar'
import { EmptyState, LoadingState, ErrorState } from './ui'
import { FloatingCopilot } from './FloatingCopilot'

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
      { label: 'Reports', path: '/reports', requiredAction: 'view', glyph: '▤' },
    ],
  },
  {
    label: 'Data Governance',
    items: [
      { label: 'Data Quality', path: '/data-quality', requiredAction: 'view', glyph: '✔' },
      { label: 'Identity & Merges', path: '/identity', requiredAction: 'view', glyph: '⧉' },
    ],
  },
  { label: 'Intelligence', items: [{ label: 'Copilot', path: '/copilot', requiredAction: 'view', glyph: '✦' }] },
]

const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items)

const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  ALL_NAV_ITEMS.map((item) => [item.path, item.label])
)

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname()
  const router = useRouter()
  const { user, roles, can, isLoading, logout } = useAuth()
  const { status: datasetStatus, errorMessage: datasetError, refresh: refreshDataset } = useDatasetStatus()

  // Route protection
  useEffect(() => {
    if (!isLoading) {
      if (!user && pathname !== '/login') {
        router.replace('/login')
      } else if (user && pathname === '/login') {
        router.replace('/')
      }
    }
  }, [isLoading, user, pathname, router])

  // If on /login page, don't show the AppShell chrome (sidebar, header, filter bar)
  if (pathname === '/login') {
    return <>{children}</>
  }

  // If loading auth state or unauthenticated on a protected page, show clean minimal spinner
  if (isLoading || !user) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)] rounded-full animate-spin" />
          <span className="text-xs text-[var(--color-text-secondary)] font-medium">Loading session…</span>
        </div>
      </div>
    )
  }

  const currentRole = roles[0] || 'Platform Administrator'
  const currentTitle = PAGE_TITLES[pathname] || 'Marine Time & Motion'
  const showScopeFilter = SCOPE_FILTER_PATHS.has(pathname)
  const isIngestionPage = pathname === '/ingestion'
  const showDatasetGate = !isIngestionPage && datasetStatus !== 'ready' && datasetStatus !== 'loading'

  // User initials for header avatar
  const displayName = user.name || 'User'
  const initials =
    displayName
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((n) => n[0].toUpperCase())
      .join('') || 'U'

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

        {/* Bottom sidebar status indicator (clean, unobtrusive, no large role selector) */}
        <div className="px-4 py-3 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-tertiary)] flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-good)] inline-block" />
            <span>Operational System</span>
          </span>
          <span className="font-mono text-[10px]">v1.0</span>
        </div>
      </aside>

      {/* Main workspace */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header with Title on Left, Compact User Identity & Sign Out on Right */}
        <header className="h-14 flex-shrink-0 px-6 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)]">
          <h1 className="text-sm font-semibold text-[var(--color-text-primary)]">{currentTitle}</h1>

          {/* Compact User Menu & Sign Out */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5 py-1 px-2.5 rounded-md bg-[var(--color-surface-muted)] border border-[var(--color-border)]">
              <span className="w-6 h-6 rounded-full bg-[var(--color-accent-soft)] border border-[var(--color-accent-soft-border)] text-[var(--color-accent)] font-semibold text-[11px] flex items-center justify-center flex-shrink-0">
                {initials}
              </span>
              <div className="flex flex-col text-left">
                <span className="text-xs font-medium text-[var(--color-text-primary)] leading-none max-w-[150px] truncate">
                  {displayName}
                </span>
                <span className="text-[10px] text-[var(--color-text-tertiary)] leading-tight mt-0.5 max-w-[150px] truncate">
                  {currentRole}
                </span>
              </div>
            </div>

            <button
              onClick={async () => {
                await logout()
                router.push('/login')
              }}
              className="text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-critical)] px-2.5 py-1.5 rounded-md hover:bg-[var(--color-surface-muted)] transition-colors cursor-pointer"
              title="Sign out of active session"
            >
              Sign out
            </button>
          </div>
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
      <FloatingCopilot />
    </div>
  )
}
