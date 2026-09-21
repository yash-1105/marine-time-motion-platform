'use client'

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth, ALL_ROLES } from '@/lib/auth-context'
import { ChevronDown, LogIn, ShieldCheck } from 'lucide-react'
import { BrandMark } from '@/components/BrandMark'

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
    <div className="min-h-screen w-screen flex items-center justify-center bg-[var(--color-bg)] px-6 py-12 relative overflow-hidden">
      <div className="absolute inset-y-0 left-0 hidden w-[42%] bg-[var(--color-accent-strong)] lg:block" aria-hidden="true" />
      <div className="absolute left-[8%] top-[16%] hidden h-64 w-64 rounded-full border border-white/10 lg:block" aria-hidden="true" />
      <div className="relative w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-20 items-center">
        {/* Left column: Brand and product purpose */}
        <div className="md:pr-6 lg:text-white">
          <div className="mb-6 flex items-center gap-3">
            <BrandMark className="h-10 w-10" />
            <span className="text-sm font-semibold tracking-tight">Marine Time &amp; Motion</span>
          </div>
          <div className="inline-flex items-center gap-2 mb-4 px-2.5 py-1 rounded-md bg-white/10 border border-white/15">
            <ShieldCheck size={13} aria-hidden="true" />
            <span className="text-[10px] font-semibold tracking-[0.09em] uppercase lg:text-white/80 text-[var(--color-text-secondary)]">
              Port Marine Operations
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-[-0.035em] text-[var(--color-text-primary)] lg:text-white leading-tight">
            Operational clarity,<br />from arrival to departure.
          </h1>
          <p className="mt-4 text-sm lg:text-white/70 text-[var(--color-text-secondary)] max-w-sm leading-6">
            Governed time-and-motion analytics for precise, traceable port operations decisions.
          </p>
        </div>

        {/* Right column: Clean, light SaaS Login Card */}
        <div className="w-full max-w-md mx-auto md:mx-0">
          <div className="bg-white rounded-[var(--radius-lg)] border border-[var(--color-border)] shadow-[var(--shadow-panel)] p-8 sm:p-10">
            <div className="mb-7">
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-[var(--color-text-primary)]">Sign in</h2>
              <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Continue to your operational workspace</p>
            </div>

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
                  className="block text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)] mb-1.5"
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
                  className="w-full bg-[var(--color-surface-subtle)] border border-[var(--color-border-strong)] rounded-[var(--radius-md)] px-3.5 py-2.5 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-accent)] focus:bg-white"
                />
              </div>

              <div>
                <label
                  htmlFor="role"
                  className="block text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)] mb-1.5"
                >
                  Role
                </label>
                <div className="relative">
                  <select
                    id="role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full bg-[var(--color-surface-subtle)] border border-[var(--color-border-strong)] rounded-[var(--radius-md)] px-3.5 py-2.5 text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)] focus:bg-white cursor-pointer appearance-none pr-10"
                  >
                    {ALL_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-[var(--color-text-secondary)]">
                    <ChevronDown size={16} aria-hidden="true" />
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-6 py-2.5 px-4 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-[var(--radius-md)] text-sm font-semibold shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Signing in…</span>
                  </>
                ) : (
                  <><LogIn size={15} aria-hidden="true" /><span>Login</span></>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
