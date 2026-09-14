import type { Metadata } from 'next'
import './globals.css'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Marine Time & Motion Platform',
  description: 'Port Marine Operations Time Release Platform',
}

const NAV_ITEMS = [
  { label: 'Home / Executive Overview', path: '/' },
  { label: 'Live Operations', path: '/live-operations' },
  { label: 'Vessel Calls', path: '/vessel-calls' },
  { label: 'Vessel Journey', path: '/vessel-journey' },
  { label: 'Time and Motion Analysis', path: '/time-and-motion' },
  { label: 'KPIs', path: '/kpis' },
  { label: 'Delays and Bottlenecks', path: '/delays' },
  { label: 'Resources', path: '/resources' },
  { label: 'Data Quality', path: '/data-quality' },
  { label: 'Data Ingestion', path: '/ingestion' },
  { label: 'Reports', path: '/reports' },
  { label: 'Copilot', path: '/copilot' },
  { label: 'Alerts and Actions', path: '/alerts' },
  { label: 'Master Data', path: '/master-data' },
  { label: 'Configuration', path: '/config' },
  { label: 'Administration', path: '/admin' },
  { label: 'Audit and Lineage', path: '/audit' },
]

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="flex h-screen bg-gray-50 text-gray-900">
        {/* Sidebar */}
        <aside className="w-64 bg-slate-900 text-slate-100 flex-shrink-0 flex flex-col h-full overflow-y-auto">
          <div className="p-4 border-b border-slate-700 font-semibold text-lg">
            Marine T&M Platform
          </div>
          <nav className="flex-1 py-4">
            <ul className="space-y-1">
              {NAV_ITEMS.map((item) => (
                <li key={item.path}>
                  <Link 
                    href={item.path} 
                    className="block px-4 py-2 hover:bg-slate-800 hover:text-white transition-colors"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-white">
          <header className="h-16 border-b flex items-center px-8 bg-white shadow-sm flex-shrink-0">
            {/* Future global filters */}
            <div className="text-sm text-gray-500">Global Filters: Not Configured</div>
          </header>
          <div className="flex-1 p-8">
            {children}
          </div>
        </main>
      </body>
    </html>
  )
}
