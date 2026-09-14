'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '../lib/auth-context'
import { SyntheticBanner } from './SyntheticBanner'

interface NavItem {
  label: string
  path: string
  requiredAction: string
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
  { label: 'Home / Executive Overview', path: '/', requiredAction: 'view' },
  { label: 'Live Operations', path: '/live-operations', requiredAction: 'view' },
  { label: 'Vessel Calls', path: '/vessel-calls', requiredAction: 'view' },
  { label: 'Vessel Journey', path: '/vessel-journey', requiredAction: 'view' },
  { label: 'Time and Motion Analysis', path: '/time-and-motion', requiredAction: 'view' },
  { label: 'KPIs', path: '/kpis', requiredAction: 'view' },
  { label: 'Delays and Bottlenecks', path: '/delays', requiredAction: 'view' },
  { label: 'Resources', path: '/resources', requiredAction: 'view' },
  { label: 'Data Quality', path: '/data-quality', requiredAction: 'approve' },
  { label: 'Data Ingestion', path: '/ingestion', requiredAction: 'create' },
  { label: 'Reports', path: '/reports', requiredAction: 'publish' },
  { label: 'Copilot', path: '/copilot', requiredAction: 'view' },
  { label: 'Alerts and Actions', path: '/alerts', requiredAction: 'view' },
  { label: 'Master Data', path: '/master-data', requiredAction: 'edit' },
  { label: 'Configuration', path: '/config', requiredAction: 'configure' },
  { label: 'Administration', path: '/admin', requiredAction: 'administer' },
  { label: 'Audit and Lineage', path: '/audit', requiredAction: 'audit' },
]

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname()
  const { user, roles, permissions, isSynthetic, can, switchRole, logout } = useAuth()

  const currentRole = roles[0] || 'Platform Administrator'

  // Filter navigation items by permission action payload from API
  const visibleNavItems = NAV_ITEMS.filter((item) => can(item.requiredAction))

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-50 text-slate-900">
      {/* 1. Mandatory Synthetic Data Banner */}
      <SyntheticBanner isSynthetic={isSynthetic} />

      <div className="flex flex-1 overflow-hidden">
        {/* 2. Sidebar with Role-Aware Navigation */}
        <aside className="w-64 bg-slate-900 text-slate-200 flex flex-col flex-shrink-0 border-r border-slate-800">
          <div className="p-4 border-b border-slate-800 font-bold text-base tracking-wide flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span>
            Marine T&amp;M Platform
          </div>

          <div className="px-4 py-3 bg-slate-800/50 border-b border-slate-800">
            <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mb-1">
              Active Role
            </div>
            <div className="text-xs font-medium text-emerald-400 truncate">
              {currentRole}
            </div>
          </div>

          <nav className="flex-1 py-3 overflow-y-auto" aria-label="Primary Navigation">
            <ul className="space-y-0.5 px-2">
              {visibleNavItems.map((item) => {
                const isActive = pathname === item.path
                return (
                  <li key={item.path}>
                    <Link
                      href={item.path}
                      className={`block px-3 py-2 text-xs rounded transition-colors ${
                        isActive
                          ? 'bg-emerald-600 text-white font-medium'
                          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      {item.label}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </nav>

          <div className="p-3 border-t border-slate-800 text-[11px] text-slate-500">
            <span>Permissions: {permissions.length} actions</span>
          </div>
        </aside>

        {/* 3. Main Workspace */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
          <header className="h-14 border-b border-slate-200 flex items-center justify-between px-6 bg-white shadow-xs flex-shrink-0">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-slate-700">Scope:</span>
              <span className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs text-slate-600">
                Tenant: {user?.data_scope?.tenant_id || 'synthetic'}
              </span>
              <span className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-xs text-slate-600">
                Port: {user?.data_scope?.port_id || '*'}
              </span>
            </div>

            {/* Role Switcher (Development Tooling) */}
            <div className="flex items-center gap-3">
              <label htmlFor="role-select" className="text-xs text-slate-500 font-medium">
                Switch Dev Role:
              </label>
              <select
                id="role-select"
                value={currentRole}
                onChange={(e) => switchRole(e.target.value)}
                className="text-xs border border-slate-300 rounded px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-emerald-500 text-slate-800 font-medium"
              >
                {ALL_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                onClick={() => logout()}
                className="text-xs px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium transition-colors"
              >
                Sign Out
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto p-6 bg-slate-50">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
