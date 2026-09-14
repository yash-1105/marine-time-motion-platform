'use client'

import React, { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function AlertsRedirectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/delays?tab=alerts')
  }, [router])

  return (
    <div className="flex h-full w-full items-center justify-center p-8 text-slate-500">
      <div className="text-center space-y-2">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600 mx-auto"></div>
        <p className="text-sm">Loading Alerts &amp; Operational Actions...</p>
      </div>
    </div>
  )
}
