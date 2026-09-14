import type { Metadata } from 'next'
import './globals.css'
import { AuthProvider } from '../lib/auth-context'
import { AppShell } from '../components/AppShell'

export const metadata: Metadata = {
  title: 'Marine Time & Motion Platform',
  description: 'Port Marine Operations Time Release Platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  )
}
