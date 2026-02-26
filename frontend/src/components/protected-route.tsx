import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'

export function ProtectedRoute() {
  const { mode, token, user, isHydrated } = useAuthStore()
  const location = useLocation()
  const authenticated = mode === 'registered' ? Boolean(token && user) : mode === 'guest'

  if (!isHydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </div>
    )
  }

  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
