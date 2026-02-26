import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type AuthMode = 'anonymous' | 'guest' | 'registered'

export interface AuthUser {
  id: number
  email: string
  name: string | null
  customer_id?: number | null
  customer?: {
    id: number
    firstname: string
    lastname: string
    email?: string | null
    phoneno?: string | null
  } | null
}

interface AuthState {
  mode: AuthMode
  token: string | null
  user: AuthUser | null
  isHydrated: boolean
  setAuth: (token: string, user: AuthUser) => void
  enterGuest: () => void
  logout: () => void
  setHydrated: () => void
}

const AUTH_STORAGE_KEY = 'auth-storage'

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      mode: 'anonymous',
      token: null,
      user: null,
      isHydrated: false,
      setAuth: (token, user) => set({ mode: 'registered', token, user }),
      enterGuest: () => set({ mode: 'guest', token: null, user: null }),
      logout: () => set({ mode: 'anonymous', token: null, user: null }),
      setHydrated: () => set({ isHydrated: true }),
    }),
    {
      name: AUTH_STORAGE_KEY,
      version: 2,
      migrate: (persistedState: unknown, version: number) => {
        const incoming = (persistedState ?? {}) as Partial<AuthState>
        if (version < 2) {
          const token = incoming.token ?? null
          const user = incoming.user ?? null
          return {
            ...incoming,
            mode: token && user ? 'registered' : 'anonymous',
          } as Partial<AuthState>
        }
        return incoming
      },
      partialize: (state) => ({ mode: state.mode, token: state.token, user: state.user }),
      onRehydrateStorage: () => () => {
        setTimeout(() => useAuthStore.getState().setHydrated(), 0)
      },
    }
  )
)

export function getToken(): string | null {
  return useAuthStore.getState().token
}

export function isAuthenticated(): boolean {
  const { mode, token, user } = useAuthStore.getState()
  return mode === 'registered' && Boolean(token && user)
}
