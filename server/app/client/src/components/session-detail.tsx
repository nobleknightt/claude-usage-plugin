import { useEffect, useState } from "react"
import { ArrowLeft } from "lucide-react"
import { NavLink, useParams } from "react-router"

import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fetchSessionTurns, type TurnRow } from "@/lib/api"

const numberFormat = new Intl.NumberFormat("en-US")
const costFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

function turnTime(t: TurnRow): string {
  const iso = t.ended_at || t.timestamp
  return iso ? new Date(iso).toLocaleString() : "—"
}

/** Turn-by-turn timeline for a single session. */
export function SessionDetail() {
  const { sessionId = "" } = useParams()
  const [turns, setTurns] = useState<TurnRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchSessionTurns(sessionId)
      .then(setTurns)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [sessionId])

  return (
    <div>
      <NavLink
        to="/sessions"
        className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Sessions
      </NavLink>
      <h2 className="font-heading text-lg font-medium">Session timeline</h2>
      <p className="mb-3 truncate text-sm text-muted-foreground" title={sessionId}>
        {loading ? "Loading…" : `${turns.length} turn(s)`} · {sessionId}
        {error && <span className="text-destructive"> — {error}</span>}
      </p>
      <ScrollArea className="w-full rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-right">Turn</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Input</TableHead>
              <TableHead className="text-right">Output</TableHead>
              <TableHead className="text-right">Cache R/W</TableHead>
              <TableHead className="text-right">Cost</TableHead>
              <TableHead>Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {turns.map((t) => (
              <TableRow key={t.turn_index}>
                <TableCell className="text-right font-mono">{t.turn_index}</TableCell>
                <TableCell className="text-muted-foreground">{t.model || "—"}</TableCell>
                <TableCell className="text-right font-mono">{numberFormat.format(t.input_tokens)}</TableCell>
                <TableCell className="text-right font-mono">{numberFormat.format(t.output_tokens)}</TableCell>
                <TableCell className="text-right font-mono text-muted-foreground">
                  {numberFormat.format(t.cache_read)}/{numberFormat.format(t.cache_write)}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {costFormat.format(t.cost_usd)}
                  {t.cost_source === "computed" && (
                    <span className="ml-1 text-xs text-muted-foreground" title="Estimated from tokens × model pricing">~</span>
                  )}
                  {t.cost_source === "unpriced" && (
                    <span className="ml-1 text-xs text-muted-foreground" title="Model not in pricing table">?</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{turnTime(t)}</TableCell>
              </TableRow>
            ))}
            {!loading && turns.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  No turns recorded for this session.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  )
}
