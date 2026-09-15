'use client'

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth, ALL_ROLES } from '@/lib/auth-context'

export default function LoginPage() {
  const router = useRouter()
  const { user, login, isLoading: authLoading } = useAuth()
  const [name, setName] = useState('')
  const [role, setRole] = useState('Platform Administrator')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // If already authenticated, redirect to home
  useEffect(() => {
    if (!authLoading && user) {
      router.replace('/')
    }
  }, [authLoading, user, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    const trimmedName = name.trim()
    if (!trimmedName) {
      setError('Please enter your name.')
      return
    }

    if (!role) {
      setError('Please select a role.')
      return
    }

    setIsSubmitting(true)
    try {
      await login(trimmedName, role)
      router.push('/')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to sign in. Please try again.'
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-[#f8fafc] px-6 py-12">
      <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center">
        {/* Left column: Brand and product purpose */}
        <div className="md:pr-6">
          <div className="inline-flex items-center gap-2 mb-4 px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200/80">
            <span className="w-2 h-2 rounded-full bg-[#0f766e]" />
            <span className="text-[11px] font-medium tracking-wide uppercase text-slate-600">
              Port Marine Operations
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-slate-900 leading-tight">
            Marine Time &amp; Motion
          </h1>
          <p className="mt-3 text-base text-slate-500 max-w-sm leading-relaxed">
            Operational time &amp; motion analytics for marine port operations.
          </p>
        </div>

        {/* Right column: Clean, light SaaS Login Card */}
        <div className="w-full max-w-md mx-auto md:mx-0">
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.06)] p-8 sm:p-10">
            <h2 className="text-xl font-semibold text-slate-900 mb-6">Sign in</h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div
                  role="alert"
                  className="p-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md font-medium"
                >
                  {error}
                </div>
              )}

              <div>
                <label
                  htmlFor="name"
                  className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5"
                >
                  Name
                </label>
                <input
                  id="name"
                  type="text"
                  autoComplete="name"
                  placeholder="Enter your name"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value)
                    if (error) setError(null)
                  }}
                  className="w-full bg-[#f8fafc] border border-slate-200 rounded-md px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white transition-all"
                />
              </div>

              <div>
                <label
                  htmlFor="role"
                  className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5"
                >
                  Role
                </label>
                <div className="relative">
                  <select
                    id="role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full bg-[#f8fafc] border border-slate-200 rounded-md px-3.5 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:bg-white transition-all cursor-pointer appearance-none pr-10"
                  >
                    {ALL_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-slate-500">
                    <svg className="w-4 h-4 fill-current" viewBox="0 0 20 20" aria-hidden="true">
                      <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
                    </svg>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-6 py-2.5 px-4 bg-[#0d3b37] hover:bg-[#082825] active:bg-[#051c1a] text-white rounded-md text-sm font-medium transition-colors shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Signing in…</span>
                  </>
                ) : (
                  <span>Login</span>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
