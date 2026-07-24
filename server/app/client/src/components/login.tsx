import { Activity, LogIn } from "lucide-react"

import { Button } from "@/components/ui/button"
import { loginUrl } from "@/lib/api"

/** Full-page sign-in prompt shown when there is no active session. */
export function Login() {
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
        <div className="mt-6 flex justify-center">
          {/* A full-page navigation (not fetch) so the OIDC redirect works. */}
          <Button asChild size="lg">
            <a href={loginUrl()}>
              <LogIn />
              Sign in with Microsoft
            </a>
          </Button>
        </div>
      </div>
    </div>
  )
}
