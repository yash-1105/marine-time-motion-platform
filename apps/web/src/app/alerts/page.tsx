'use client'

import React, { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { LoadingState } from '@/components/ui'

export default function AlertsRedirectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/delays?tab=alerts')
  }, [router])

  return (
    <div className="flex h-full w-full items-center justify-center p-8">
      <LoadingState label="Loading Alerts & Operational Actions…" />
    </div>
  )
}
