import Link from 'next/link'
import { Compass } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-accent)] shadow-[var(--shadow-xs)]"><Compass size={22} /></div>
      <h2 className="text-xl font-semibold tracking-tight text-[var(--color-text-primary)]">Page not found</h2>
      <p className="mt-1 max-w-sm text-sm text-[var(--color-text-secondary)]">The requested route is not available in this operational workspace.</p>
      <Link href="/" className="mt-5 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--color-accent-hover)]">Return to dashboard</Link>
    </div>
  )
}
