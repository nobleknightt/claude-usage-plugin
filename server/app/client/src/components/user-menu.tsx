import { LogOut } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Me } from "@/lib/api"

/** Prefer the Entra display name; fall back to the email local-part. */
function words(me: Me): string[] {
  const source = me.name?.trim() || me.email.split("@")[0]
  return source.split(/[\s.\-_]+/).filter(Boolean)
}

function initials(me: Me): string {
  const w = words(me)
  return ((w[0]?.[0] ?? "?") + (w[1]?.[0] ?? "")).toUpperCase()
}

function displayName(me: Me): string {
  return me.name?.trim() || words(me).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ")
}

/** Account avatar in the top bar; opens a menu with identity + sign out. */
export function UserMenu({ me, onLogout }: { me: Me; onLogout: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" className="rounded-full" aria-label="Account">
          <span className="text-xs font-medium">{initials(me)}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-1 font-normal">
          <span className="font-medium">{displayName(me)}</span>
          <span className="truncate text-xs text-muted-foreground" title={me.email}>
            {me.email}
          </span>
          <Badge variant="secondary" className="mt-1 w-fit">
            {me.is_admin ? "Admin" : "Member"}
          </Badge>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
