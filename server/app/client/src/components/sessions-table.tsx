import { useEffect, useMemo, useState } from "react"

import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { UserFilter } from "@/components/user-filter"
import { fetchSessions, type SessionRow } from "@/lib/api"

const numberFormat = new Intl.NumberFormat("en-US")
const costFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

function dirLabel(path: string): string {
  if (!path) return "—"
  const parts = path.replace(/[/\\]+$/, "").split(/[/\\]/)
  return parts[parts.length - 1] || path
}

/** One row per session — the individual ingested records, not just aggregates. */
export function SessionsTable() {
  const [allRows, setAllRows] = useState<SessionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedEmail, setSelectedEmail] = useState("")

  useEffect(() => {
    fetchSessions({ limit: 500 })
      .then(setAllRows)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  const users = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.email))).sort(),
    [allRows]
  )
  const rows = selectedEmail ? allRows.filter((r) => r.email === selectedEmail) : allRows
  // Only admins / account owners ever see more than one user, so the filter
  // naturally only appears for them.
  const showFilter = users.length > 1

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-lg font-medium">Sessions</h2>
          <p className="text-sm text-muted-foreground">
            {loading ? "Loading…" : `${rows.length} session(s)`}
            {error && <span className="text-destructive"> — {error}</span>}
          </p>
        </div>
        {showFilter && (
          <UserFilter users={users} value={selectedEmail} onChange={setSelectedEmail} />
        )}
      </div>
      <ScrollArea className="w-full rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Directory</TableHead>
              <TableHead>Account</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Turns</TableHead>
              <TableHead className="text-right">Input</TableHead>
              <TableHead className="text-right">Output</TableHead>
              <TableHead className="text-right">Cache R/W</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead>Last activity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.session_id}>
                <TableCell className="font-medium">{s.email}</TableCell>
                <TableCell title={s.cwd} className="max-w-40 truncate">
                  {dirLabel(s.cwd)}
                </TableCell>
                <TableCell className="text-muted-foreground">{s.account_email || "—"}</TableCell>
                <TableCell className="text-muted-foreground">{s.model || "—"}</TableCell>
                <TableCell className="text-right">{numberFormat.format(s.turns)}</TableCell>
                <TableCell className="text-right font-mono">{numberFormat.format(s.input_tokens)}</TableCell>
                <TableCell className="text-right font-mono">{numberFormat.format(s.output_tokens)}</TableCell>
                <TableCell className="text-right font-mono text-muted-foreground">
                  {numberFormat.format(s.cache_read)}/{numberFormat.format(s.cache_write)}
                </TableCell>
                <TableCell className="text-right font-mono">{costFormat.format(s.cost_usd)}</TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(s.last_turn_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
            {!loading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="text-center text-muted-foreground">
                  No sessions recorded yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  )
}
