import { LogIn } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { loginUrl } from "@/lib/api"

/** Full-page sign-in prompt shown when there is no active session. */
export function Login() {
  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="font-heading text-xl">Claude Usage Tracker</CardTitle>
          <CardDescription>Sign in to view usage and manage your API keys.</CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          {/* A full-page navigation (not fetch) so the OIDC redirect works. */}
          <Button asChild size="lg">
            <a href={loginUrl()}>
              <LogIn />
              Sign in with Microsoft
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
