import { useEffect, useState } from "react"
import { CircleAlert, CircleCheck } from "lucide-react"

import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fetchAccounts, type AccountRow } from "@/lib/api"

const numberFormat = new Intl.NumberFormat("en-US")
const compactFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 })
const costFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

/** Reconciliation of usage by shared Claude account. */
export function AccountsTable() {
  const [rows, setRows] = useState<AccountRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAccounts()
      .then(setRows)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="mb-3">
        <h2 className="font-heading text-lg font-medium">Accounts</h2>
        <p className="text-sm text-muted-foreground">
          {loading ? "Loading…" : `${rows.length} account(s) — usage grouped by the Claude account it bills to`}
          {error && <span className="text-destructive"> — {error}</span>}
        </p>
      </div>
      <ScrollArea className="w-full rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Account</TableHead>
              <TableHead className="text-right">Users</TableHead>
              <TableHead className="text-right">Sessions</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead>Owner logged in</TableHead>
              <TableHead>Last activity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((a) => (
              <TableRow key={a.account_email}>
                <TableCell className="font-medium">{a.account_email || "—"}</TableCell>
                <TableCell className="text-right">{numberFormat.format(a.users)}</TableCell>
                <TableCell className="text-right">{numberFormat.format(a.sessions)}</TableCell>
                <TableCell className="text-right font-mono">{compactFormat.format(a.tokens)}</TableCell>
                <TableCell className="text-right font-mono">{costFormat.format(a.cost_usd)}</TableCell>
                <TableCell>
                  {a.owner_registered ? (
                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                      <CircleCheck className="size-4 text-emerald-600" /> Yes
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-muted-foreground"
                      title="No user with this account's address has signed in, so no one sees the whole account."
                    >
                      <CircleAlert className="size-4 text-amber-600" /> No
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(a.last_seen).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
            {!loading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  No accounts recorded yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  )
}
