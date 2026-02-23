/**
 * Ada frontend — auth API client functions
 *
 * Thin wrappers over the /api/auth/* REST endpoints. Token storage uses
 * localStorage. The access token is keyed ADA_ACCESS_TOKEN; the refresh
 * token is keyed ADA_REFRESH_TOKEN. Both keys are exported so other modules
 * (e.g. client.ts) can read the stored access token without importing auth.ts
 * directly.
 *
 * @decision DEC-FRONTEND-011
 * @title localStorage for token storage — no httpOnly cookie in Phase 2
 * @status accepted
 * @rationale httpOnly cookies are the gold standard but require server-side
 *   Set-Cookie support and same-site configuration. For Phase 2 the backend
 *   returns tokens in JSON response bodies (the FastAPI auth routes follow
 *   the OAuth2 bearer pattern). localStorage is the pragmatic choice for a
 *   React SPA talking to a separate API origin. A future phase can migrate
 *   to httpOnly cookies with a BFF proxy. The XSS risk is accepted for now
 *   given this is a non-production prototype.
 */

const BASE = '/api/auth'

export const TOKEN_KEY = 'ADA_ACCESS_TOKEN'
export const REFRESH_KEY = 'ADA_REFRESH_TOKEN'

// ---------------------------------------------------------------------------
// Token storage helpers
// ---------------------------------------------------------------------------

export function storeTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_KEY, refreshToken)
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

// ---------------------------------------------------------------------------
// Auth API calls
// ---------------------------------------------------------------------------

export interface AuthTokens {
  access_token: string
  refresh_token: string
}

export interface UserProfile {
  id: string
  email: string
  role: string
  patient_id: string | null
  created_at: string
  is_active: boolean
}

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`Auth API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

/**
 * Register a new user account.
 * Returns the created user profile (no tokens — user must then log in).
 */
export async function register(email: string, password: string): Promise<UserProfile> {
  return authFetch<UserProfile>('/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/**
 * Authenticate with email+password.
 * Stores the returned token pair in localStorage.
 */
export async function login(email: string, password: string): Promise<AuthTokens> {
  const tokens = await authFetch<AuthTokens>('/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  storeTokens(tokens.access_token, tokens.refresh_token)
  return tokens
}

/**
 * Exchange the stored refresh token for a new access+refresh token pair.
 * Updates localStorage with the new tokens.
 * Throws if no refresh token is stored or the server rejects it.
 */
export async function refresh(): Promise<AuthTokens> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('No refresh token stored')
  }
  const tokens = await authFetch<AuthTokens>('/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  storeTokens(tokens.access_token, tokens.refresh_token)
  return tokens
}

/**
 * Fetch the currently authenticated user's profile.
 * Caller must supply a valid access token.
 */
export async function me(token: string): Promise<UserProfile> {
  return authFetch<UserProfile>('/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
}
