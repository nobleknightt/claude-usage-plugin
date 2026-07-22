import { useEffect, useMemo, useState } from "react"
import {
  ArrowDown,
  ArrowUp,
  CircleDollarSign,
  Coins,
  Layers,
  LogOut,
  Users,
  type LucideIcon,
} from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts"

import { ApiKeys } from "@/components/api-keys"
import { Login } from "@/components/login"
import { ModeToggle } from "@/components/mode-toggle"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  fetchMe,
  fetchSummary,
  logout,
  type Me,
  type UserSummary,
} from "@/lib/api"

type SortKey = keyof Pick<
  UserSummary,
  "email" | "sessions" | "input_tokens" | "output_tokens" | "cost_usd"
>

const numberFormat = new Intl.NumberFormat("en-US")
const costFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

const chartConfig: ChartConfig = {
  input_tokens: { label: "Input tokens", color: "var(--chart-1)" },
  output_tokens: { label: "Output tokens", color: "var(--chart-2)" },
}

/**
 * Auth gate: load the current user, show the login screen if unauthenticated,
 * otherwise render the dashboard.
 */
function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then((user) => !cancelled && setMe(user))
      .catch(() => !cancelled && setMe(null))
      .finally(() => !cancelled && setChecking(false))
    return () => {
      cancelled = true
    }
  }, [])

  if (checking) {
    return <div className="flex min-h-svh items-center justify-center text-muted-foreground">Loading…</div>
  }
  if (!me) return <Login />
  return <Dashboard me={me} />
}

function Dashboard({ me }: { me: Me }) {
  const [rows, setRows] = useState<UserSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>("cost_usd")
  const [sortDesc, setSortDesc] = useState(true)

  async function handleLogout() {
    try {
      await logout()
    } catch {
      // ignore — clearing the session below still returns the user to login
    }
    window.location.reload()
  }

  useEffect(() => {
    let cancelled = false

    fetchSummary()
      .then((data) => {
        if (!cancelled) setRows(data)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const totals = useMemo(
    () =>
      rows.reduce(
        (acc, row) => ({
          sessions: acc.sessions + row.sessions,
          input_tokens: acc.input_tokens + row.input_tokens,
          output_tokens: acc.output_tokens + row.output_tokens,
          cost_usd: acc.cost_usd + row.cost_usd,
        }),
        { sessions: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0 }
      ),
    [rows]
  )

  const sortedRows = useMemo(() => {
    const sorted = [...rows].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === "string" || typeof bv === "string") {
        return String(av).localeCompare(String(bv))
      }
      return (av as number) - (bv as number)
    })
    return sortDesc ? sorted.reverse() : sorted
  }, [rows, sortKey, sortDesc])

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDesc((desc) => !desc)
    } else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">
            Claude Usage Tracker
          </h1>
          <p className="text-sm text-muted-foreground">
            Per-user token and cost usage across the shared account.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
            {me.email}
            {me.is_admin && <Badge variant="secondary">Admin</Badge>}
          </span>
          <ModeToggle />
          <Button variant="outline" size="sm" onClick={handleLogout}>
            <LogOut />
            Sign out
          </Button>
        </div>
      </header>

      {error && (
        <p className="text-sm text-destructive">
          Could not load usage data: {error}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={Users} label="Users" value={numberFormat.format(rows.length)} />
        <StatCard
          icon={Layers}
          label="Sessions"
          value={numberFormat.format(totals.sessions)}
        />
        <StatCard
          icon={Coins}
          label="Total tokens"
          value={numberFormat.format(
            totals.input_tokens + totals.output_tokens
          )}
        />
        <StatCard
          icon={CircleDollarSign}
          label="Cost"
          value={costFormat.format(totals.cost_usd)}
        />
      </div>

      <section>
        <h2 className="font-heading text-lg font-medium">Tokens by user</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Input vs. output tokens per user
        </p>
        <ChartContainer config={chartConfig} className="aspect-auto h-72 w-full">
          <BarChart data={rows} margin={{ left: 12, right: 12 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="email"
              tickLine={false}
              axisLine={false}
              tickFormatter={(email: string) => email.split("@")[0]}
            />
            <YAxis tickLine={false} axisLine={false} width={48} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="input_tokens" fill="var(--color-input_tokens)" radius={4} />
            <Bar dataKey="output_tokens" fill="var(--color-output_tokens)" radius={4} />
          </BarChart>
        </ChartContainer>
      </section>

      <section>
        <h2 className="font-heading text-lg font-medium">Per-user summary</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          {loading ? "Loading…" : `${rows.length} user(s)`}
        </p>
        <Table>
            <TableHeader>
              <TableRow>
                <SortableHead label="Email" sortKey="email" active={sortKey} desc={sortDesc} onClick={toggleSort} />
                <TableHead>Account</TableHead>
                <SortableHead label="Sessions" sortKey="sessions" active={sortKey} desc={sortDesc} onClick={toggleSort} />
                <SortableHead label="Input tokens" sortKey="input_tokens" active={sortKey} desc={sortDesc} onClick={toggleSort} />
                <SortableHead label="Output tokens" sortKey="output_tokens" active={sortKey} desc={sortDesc} onClick={toggleSort} />
                <TableHead>Cache read</TableHead>
                <TableHead>Cache write</TableHead>
                <SortableHead label="Cost" sortKey="cost_usd" active={sortKey} desc={sortDesc} onClick={toggleSort} />
                <TableHead>Last seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedRows.map((row) => (
                <TableRow key={`${row.email}-${row.account_email}`}>
                  <TableCell className="font-medium">{row.email}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {row.account_email}
                  </TableCell>
                  <TableCell>{numberFormat.format(row.sessions)}</TableCell>
                  <TableCell className="font-mono">
                    {numberFormat.format(row.input_tokens)}
                  </TableCell>
                  <TableCell className="font-mono">
                    {numberFormat.format(row.output_tokens)}
                  </TableCell>
                  <TableCell className="font-mono">
                    {numberFormat.format(row.cache_read)}
                  </TableCell>
                  <TableCell className="font-mono">
                    {numberFormat.format(row.cache_write)}
                  </TableCell>
                  <TableCell className="font-mono">
                    {costFormat.format(row.cost_usd)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(row.last_seen).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
              {!loading && rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground">
                    No usage recorded yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
      </section>

      <section>
        <ApiKeys />
      </section>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <Card size="sm" className="rounded-lg border border-border shadow-none ring-0">
      <CardContent className="flex items-center gap-3">
        <Icon className="size-8 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="font-mono text-2xl font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function SortableHead({
  label,
  sortKey,
  active,
  desc,
  onClick,
}: {
  label: string
  sortKey: SortKey
  active: SortKey
  desc: boolean
  onClick: (key: SortKey) => void
}) {
  const isActive = active === sortKey
  return (
    <TableHead
      role="button"
      aria-sort={isActive ? (desc ? "descending" : "ascending") : "none"}
      className="cursor-pointer select-none"
      onClick={() => onClick(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive &&
          (desc ? (
            <ArrowDown className="size-3.5" />
          ) : (
            <ArrowUp className="size-3.5" />
          ))}
      </span>
    </TableHead>
  )
}

export { App }
