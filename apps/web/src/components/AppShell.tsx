'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '../lib/auth-context'
import { SyntheticBanner } from './SyntheticBanner'
import { GlobalFilterBar } from './GlobalFilterBar'

interface NavItem {
  label: string
  path: string
  requiredAction: string
  glyph: string
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

const NAV_ITEMS: NavItem[] = [
  { label: 'Executive Dashboard', path: '/', requiredAction: 'view', glyph: '🏛' },
  { label: 'Vessel Calls', path: '/vessel-calls', requiredAction: 'view', glyph: '🚢' },
  { label: 'Vessel Journey', path: '/vessel-journey', requiredAction: 'view', glyph: '⏱' },
  { label: 'Data Quality', path: '/data-quality', requiredAction: 'view', glyph: '🛡' },
  { label: 'Time & Motion Explorer', path: '/time-and-motion', requiredAction: 'view', glyph: '⚡' },
  { label: 'Governed KPIs', path: '/kpis', requiredAction: 'view', glyph: '🎯' },
  { label: 'Delays & Bottlenecks', path: '/delays', requiredAction: 'view', glyph: '⏳' },
  { label: 'Alerts & Actions', path: '/alerts', requiredAction: 'view', glyph: '🚨' },
  { label: 'Identity & Merges', path: '/identity', requiredAction: 'view', glyph: '🔗' },
  { label: 'Data Ingestion', path: '/ingestion', requiredAction: 'view', glyph: '📥' },
]

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname()
  const { user, roles, permissions, isSynthetic, can, switchRole, logout } = useAuth()

  const currentRole = roles[0] || 'Platform Administrator'

  // Filter navigation items by permission action payload from API
  const visibleNavItems = NAV_ITEMS.filter((item) => can(item.requiredAction))

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-900">
      {/* 1. Mandatory Synthetic Data Banner */}
      <SyntheticBanner isSynthetic={isSynthetic} />

      <div className="flex flex-1 overflow-hidden">
        {/* 2. Sidebar with Role-Aware Navigation */}
        <aside className="w-60 bg-slate-950 text-slate-200 flex flex-col flex-shrink-0 border-r border-slate-800">
          <div className="p-3 border-b border-slate-800 font-bold text-sm tracking-wide flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block shadow-xs shadow-emerald-400"></span>
            <span className="text-white font-semibold">Marine Control Room</span>
          </div>

          <div className="px-3 py-2 bg-slate-900/60 border-b border-slate-800">
            <div className="flex items-center justify-between">
              <label htmlFor="role-select" className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                Role Context
              </label>
              <button
                onClick={() => logout()}
                className="text-[10px] text-slate-500 hover:text-slate-300 cursor-pointer"
                title="Sign out"
              >
                Sign out
              </button>
            </div>
            <select
              id="role-select"
              aria-label="Switch Role"
              value={currentRole}
              onChange={(e) => switchRole(e.target.value)}
              className="w-full mt-1 bg-slate-950 border border-slate-800 rounded px-1.5 py-1 text-xs text-emerald-400 font-semibold focus:outline-none focus:ring-1 focus:ring-emerald-500 cursor-pointer"
            >
              {ALL_ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <div className="text-[10px] text-slate-500 truncate mt-1">
              {user?.email || 'admin@port.local'}
            </div>
          </div>

          <nav className="flex-1 py-2 overflow-y-auto" aria-label="Primary Navigation">
            <ul className="space-y-0.5 px-2">
              {visibleNavItems.map((item) => {
                const isActive = pathname === item.path
                return (
                  <li key={item.path}>
                    <Link
                      href={item.path}
                      className={`flex items-center gap-2 px-2.5 py-1.5 text-xs rounded font-medium transition-colors ${
                        isActive
                          ? 'bg-emerald-600 text-white shadow-xs'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      <span className="text-sm">{item.glyph}</span>
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </nav>

          <div className="p-3 border-t border-slate-800 text-[10px] text-slate-400 flex items-center justify-between">
            <span>Auth: {permissions.length} actions</span>
            <span className="text-emerald-400 font-bold">V1 LIVE</span>
          </div>
        </aside>

        {/* 3. Main Workspace */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-100">
          {/* Global Filter Bar wrapped in Suspense */}
          <React.Suspense fallback={<div className="h-9 bg-slate-900 border-b border-slate-800" />}>
            <GlobalFilterBar />
          </React.Suspense>

          {/* Screen Content Container */}
          <main className="flex-1 overflow-hidden flex flex-col min-w-0">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
