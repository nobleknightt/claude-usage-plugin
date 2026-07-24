import { useEffect, useState } from "react"
import { Activity } from "lucide-react"

import { Button } from "@/components/ui/button"
import { fetchProviders, loginUrl, type Providers } from "@/lib/api"

/** Microsoft four-square logo. */
function MicrosoftIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <path fill="#ff5722" d="M6 6H22V22H6z" transform="rotate(-180 14 14)" />
      <path fill="#4caf50" d="M26 6H42V22H26z" transform="rotate(-180 34 14)" />
      <path fill="#ffc107" d="M26 26H42V42H26z" transform="rotate(-180 34 34)" />
      <path fill="#03a9f4" d="M6 26H22V42H6z" transform="rotate(-180 14 34)" />
    </svg>
  )
}

/** Google "G" logo. */
function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z" />
      <path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z" />
      <path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z" />
      <path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z" />
    </svg>
  )
}

/** Full-page sign-in prompt shown when there is no active session. */
export function Login() {
  const [providers, setProviders] = useState<Providers | null>(null)

  useEffect(() => {
    fetchProviders()
      .then(setProviders)
      .catch(() => setProviders({ microsoft: false, google: false }))
  }, [])

  // Still loading providers: render nothing to avoid flashing a card.
  if (!providers) return null

  // Nothing to sign in with — show a bare notice, not the sign-in card.
  if (!providers.microsoft && !providers.google) {
    return (
      <div className="flex min-h-svh items-center justify-center p-6 text-center text-sm text-muted-foreground">
        No auth provider configured.
      </div>
    )
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6">
        <div className="flex flex-col items-center gap-1 text-center">
          <div className="mb-2 flex size-11 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <Activity className="size-5" />
          </div>
          <h1 className="font-heading text-xl font-semibold">Claude Usage</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to view usage and manage your API keys.
          </p>
        </div>
        {/* Full-page navigations (not fetch) so the OIDC redirect works. */}
        <div className="mt-6 flex flex-col gap-2">
          {providers.microsoft && (
            <Button asChild size="lg" variant="outline" className="w-full">
              <a href={loginUrl("microsoft")}>
                <MicrosoftIcon className="size-4" />
                Sign in with Microsoft
              </a>
            </Button>
          )}
          {providers.google && (
            <Button asChild size="lg" variant="outline" className="w-full">
              <a href={loginUrl("google")}>
                <GoogleIcon className="size-4" />
                Sign in with Google
              </a>
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
