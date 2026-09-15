'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'

export interface DataScope {
  tenant_id: string
  port_id?: string
  terminal_id?: string
}

export interface UserProfile {
  user_id: string
  name?: string
  email: string
  roles: string[]
  permissions: string[]
  data_scope: DataScope
  is_service_account: boolean
  is_synthetic: boolean
}

export const ALL_ROLES = [
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

interface AuthContextType {
  user: UserProfile | null
  roles: string[]
  permissions: string[]
  dataScope: DataScope | null
  isSynthetic: boolean
  isLoading: boolean
  token?: string
  can: (action: string) => boolean
  login: (name: string, roleName: string) => Promise<void>
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
  login: async () => {},
  switchRole: async () => {},
  logout: async () => {},
})

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | undefined>(undefined)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  // Initialize from persistent storage on mount
  useEffect(() => {
    const initAuth = async () => {
      try {
        if (typeof window !== 'undefined') {
          const storedUser = localStorage.getItem('auth_user')
          const storedToken = localStorage.getItem('auth_token')
          if (storedUser && storedToken) {
            try {
              const parsed: UserProfile = JSON.parse(storedUser)
              setUser(parsed)
              setToken(storedToken)
            } catch {
              localStorage.removeItem('auth_user')
              localStorage.removeItem('auth_token')
              setUser(null)
              setToken(undefined)
            }
          } else {
            setUser(null)
            setToken(undefined)
          }
        }
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [])

  const login = async (name: string, roleName: string) => {
    const cleanName = name.trim()
    if (!cleanName) {
      throw new Error('Please enter your name.')
    }
    if (!roleName) {
      throw new Error('Please select a role.')
    }

    setIsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/dev/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_or_email: roleName }),
        credentials: 'include',
      })

      if (res.ok) {
        const data = await res.json()
        const userProfile: UserProfile = {
          user_id: data.session_id,
          name: cleanName,
          email: `${roleName.toLowerCase().replace(/ /g, '_')}@port.local`,
          roles: data.roles,
          permissions: data.permissions,
          data_scope: data.data_scope,
          is_service_account: false,
          is_synthetic: true,
        }
        setToken(data.access_token)
        setUser(userProfile)
        if (typeof window !== 'undefined') {
          localStorage.setItem('auth_token', data.access_token)
          localStorage.setItem('auth_user', JSON.stringify(userProfile))
        }
      } else {
        // Fallback for offline environments
        const userProfile: UserProfile = {
          user_id: `user-${roleName.toLowerCase().replace(/ /g, '-')}`,
          name: cleanName,
          email: `${roleName.toLowerCase().replace(/ /g, '_')}@port.local`,
          roles: [roleName],
          permissions: [
            'view', 'create', 'edit', 'approve', 'reject', 'merge', 'unmerge',
            'recalculate', 'publish', 'export', 'configure', 'administer', 'audit'
          ],
          data_scope: { tenant_id: 'tenant-synthetic-01', port_id: '*', terminal_id: '*' },
          is_service_account: false,
          is_synthetic: true,
        }
        setToken('dev-token')
        setUser(userProfile)
        if (typeof window !== 'undefined') {
          localStorage.setItem('auth_token', 'dev-token')
          localStorage.setItem('auth_user', JSON.stringify(userProfile))
        }
      }
    } catch {
      // Offline fallback
      const userProfile: UserProfile = {
        user_id: `user-${roleName.toLowerCase().replace(/ /g, '-')}`,
        name: cleanName,
        email: `${roleName.toLowerCase().replace(/ /g, '_')}@port.local`,
        roles: [roleName],
        permissions: [
          'view', 'create', 'edit', 'approve', 'reject', 'merge', 'unmerge',
          'recalculate', 'publish', 'export', 'configure', 'administer', 'audit'
        ],
        data_scope: { tenant_id: 'tenant-synthetic-01', port_id: '*', terminal_id: '*' },
        is_service_account: false,
        is_synthetic: true,
      }
      setToken('dev-token')
      setUser(userProfile)
      if (typeof window !== 'undefined') {
        localStorage.setItem('auth_token', 'dev-token')
        localStorage.setItem('auth_user', JSON.stringify(userProfile))
      }
    } finally {
      setIsLoading(false)
    }
  }

  const switchRole = async (roleName: string) => {
    if (!user) return
    await login(user.name || 'User', roleName)
  }

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      // Ignore network errors on logout
    } finally {
      setUser(null)
      setToken(undefined)
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user')
      }
    }
  }

  const can = (action: string): boolean => {
    if (!user) return false
    if (user.roles.includes('Platform Administrator')) return true
    return user.permissions.includes(action)
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
        login,
        switchRole,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
