'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'

export interface DataScope {
  tenant_id: string
  port_id?: string
  terminal_id?: string
}

export interface UserProfile {
  user_id: string
  email: string
  roles: string[]
  permissions: string[]
  data_scope: DataScope
  is_service_account: boolean
  is_synthetic: boolean
}

interface AuthContextType {
  user: UserProfile | null
  roles: string[]
  permissions: string[]
  dataScope: DataScope | null
  isSynthetic: boolean
  isLoading: boolean
  token?: string
  can: (action: string) => boolean
  switchRole: (roleName: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  roles: [],
  permissions: [],
  dataScope: null,
  isSynthetic: true,
  isLoading: true,
  token: undefined,
  can: () => false,
  switchRole: async () => {},
  logout: async () => {},
})

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | undefined>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('auth_token') || 'dev-token'
    }
    return 'dev-token'
  })
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const fetchCurrentUser = async () => {
    try {
      const storedToken = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
      const headers: Record<string, string> = {}
      if (storedToken) {
        headers['Authorization'] = `Bearer ${storedToken}`
      }
      const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers,
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
      } else {
        // In local development, auto-login with Platform Administrator if not logged in
        await autoDevLogin('Platform Administrator')
      }
    } catch {
      // Fallback dev login mock for local dev preview
      setUser({
        user_id: 'dev-user-admin',
        email: 'admin@port.local',
        roles: ['Platform Administrator'],
        permissions: [
          'view', 'create', 'edit', 'approve', 'reject', 'merge', 'unmerge',
          'recalculate', 'publish', 'export', 'configure', 'administer', 'audit'
        ],
        data_scope: { tenant_id: 'tenant-synthetic-01', port_id: '*', terminal_id: '*' },
        is_service_account: false,
        is_synthetic: true,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const autoDevLogin = async (roleName: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/dev/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_or_email: roleName }),
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setToken(data.access_token)
        if (typeof window !== 'undefined') {
          localStorage.setItem('auth_token', data.access_token)
        }
        setUser({
          user_id: data.session_id,
          email: `${roleName.toLowerCase().replace(/ /g, '_')}@port.local`,
          roles: data.roles,
          permissions: data.permissions,
          data_scope: data.data_scope,
          is_service_account: false,
          is_synthetic: true,
        })
      }
    } catch {
      // Ignore network errors in static rendering / disconnected states
    }
  }

  useEffect(() => {
    fetchCurrentUser()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const can = (action: string): boolean => {
    if (!user) return false
    if (user.roles.includes('Platform Administrator')) return true
    return user.permissions.includes(action)
  }

  const switchRole = async (roleName: string) => {
    setIsLoading(true)
    await autoDevLogin(roleName)
    setIsLoading(false)
  }

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } finally {
      setUser(null)
      setToken('dev-token')
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token')
      }
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        roles: user?.roles || [],
        permissions: user?.permissions || [],
        dataScope: user?.data_scope || null,
        isSynthetic: user?.is_synthetic ?? true,
        isLoading,
        token,
        can,
        switchRole,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
