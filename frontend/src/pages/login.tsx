import { useState, useCallback } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { login } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const enterGuest = useAuthStore((s) => s.enterGuest)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/'

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      setError(null)
      setLoading(true)
      try {
        const data = await login(email, password)
        setAuth(data.access_token, {
          id: data.user.id,
          email: data.user.email,
          name: data.user.name,
          customer_id: data.user.customer_id ?? null,
          customer: data.user.customer ?? null,
        })
        navigate(from, { replace: true })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Login failed')
      } finally {
        setLoading(false)
      }
    },
    [email, password, setAuth, navigate, from]
  )

  const onContinueAsGuest = useCallback(() => {
    enterGuest()
    navigate('/', { replace: true })
  }, [enterGuest, navigate])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background grain px-4">
      <div
        className={cn(
          'w-full max-w-sm rounded-2xl border border-border bg-card p-8 shadow-lg',
          'transition-all duration-300 ease-out',
          'focus-within:shadow-xl focus-within:ring-2 focus-within:ring-ring/30 focus-within:ring-offset-2 focus-within:ring-offset-background'
        )}
      >
        <h1
          className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Welcome back
        </h1>
        <p className="text-muted-foreground text-sm mb-8">
          Sign in to continue to the fashion assistant.
        </p>

        <form onSubmit={onSubmit} className="space-y-6">
          <div>
            <label
              htmlFor="login-email"
              className="block text-sm font-medium text-foreground mb-2"
            >
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className={cn(
                'w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground',
                'placeholder:text-muted-foreground',
                'transition-all duration-200',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent',
                'disabled:opacity-50'
              )}
              placeholder="you@example.com"
              disabled={loading}
            />
          </div>
          <div>
            <label
              htmlFor="login-password"
              className="block text-sm font-medium text-foreground mb-2"
            >
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className={cn(
                'w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground',
                'placeholder:text-muted-foreground',
                'transition-all duration-200',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent',
                'disabled:opacity-50'
              )}
              placeholder="••••••••"
              disabled={loading}
            />
          </div>

          {error && (
            <p
              className="text-sm text-destructive animate-in fade-in duration-200"
              role="alert"
            >
              {error}
            </p>
          )}

          <Button
            type="submit"
            className="w-full rounded-lg py-3 font-medium transition-all duration-200 hover:opacity-90"
            disabled={loading}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{' '}
          <Link
            to="/signup"
            className="font-medium text-primary underline-offset-4 hover:underline transition-opacity"
          >
            Sign up
          </Link>
        </p>

        <Button
          type="button"
          variant="ghost"
          className="w-full mt-3 rounded-lg py-3 font-medium border border-border text-foreground bg-card/30 hover:bg-secondary/50"
          onClick={onContinueAsGuest}
        >
          Continue as Guest
        </Button>
      </div>
    </div>
  )
}
