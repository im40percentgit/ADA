/**
 * useAuth — authentication state hook
 *
 * Manages the current user session: loading the stored token on mount,
 * validating it via /api/auth/me, and exposing login/logout/register methods.
 *
 * Consumers:
 *   const { currentUser, isAuthenticated, loading, login, logout, register } = useAuth()
 *
 * The hook is intended to be called once at the App root and the result
 * passed down via props or a context. It does not use React Context itself —
 * that layer is added in App.tsx if needed.
 *
 * @decision DEC-FRONTEND-012
 * @title useAuth holds auth state at App root — no global context in Phase 2
 * @status accepted
 * @rationale In Phase 2 only App.tsx and components directly under it need
 *   auth state. Introducing a Context + Provider adds boilerplate with no
 *   benefit at this scale. If auth state is needed deeper in the tree in a
 *   future phase, the hook can be trivially wrapped in a context.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  login as apiLogin,
  register as apiRegister,
  me,
  getAccessToken,
  clearTokens,
  type UserProfile,
} from '../api/auth'

// Re-export so App.tsx can use the type without importing auth directly
export type { UserProfile }

export interface UseAuthReturn {
  currentUser: UserProfile | null
  isAuthenticated: boolean
  loading: boolean
  /** Error message from the last auth operation, or null */
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  register: (email: string, password: string, role?: string) => Promise<void>
}

export function useAuth(): UseAuthReturn {
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // On mount: check for a stored token and validate it
  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setLoading(false)
      return
    }
    me(token)
      .then((user) => {
        setCurrentUser(user)
      })
      .catch(() => {
        // Token invalid or expired and refresh failed — start fresh
        clearTokens()
        setCurrentUser(null)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setError(null)
    try {
      await apiLogin(email, password)
      const token = getAccessToken()!
      const user = await me(token)
      setCurrentUser(user)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(msg)
      throw err
    }
  }, [])

  const logout = useCallback(() => {
    clearTokens()
    setCurrentUser(null)
    setError(null)
  }, [])

  const register = useCallback(async (email: string, password: string, role?: string) => {
    setError(null)
    try {
      await apiRegister(email, password, role ?? 'user')
      // Auto-login after successful registration
      await apiLogin(email, password)
      const token = getAccessToken()!
      const user = await me(token)
      setCurrentUser(user)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Registration failed'
      setError(msg)
      throw err
    }
  }, [])

  return {
    currentUser,
    isAuthenticated: currentUser !== null,
    loading,
    error,
    login,
    logout,
    register,
  }
}

// ---------------------------------------------------------------------------
// Standalone logout helper (imported by auth.ts module)
// The actual token clearing is in clearTokens() from auth.ts.
// This re-export exists so call-sites that only import useAuth don't need
// to also import from auth.ts.
// ---------------------------------------------------------------------------

export function logout(): void {
  clearTokens()
}
