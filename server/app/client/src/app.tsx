import { useEffect, useMemo, useState } from "react"
import {
  ArrowDown,
  ArrowUp,
  CircleDollarSign,
  Coins,
  Database,
  Gauge,
  Layers,
  Users,
  type LucideIcon,
} from "lucide-react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Outlet, Route, Routes, useLocation } from "react-router"

import { ActivityHeatmap } from "@/components/activity-heatmap"
import { ApiKeys } from "@/components/api-keys"
import { AppSidebar } from "@/components/app-sidebar"
import { Login } from "@/components/login"
import { ModeToggle } from "@/components/mode-toggle"
import { SessionsTable } from "@/components/sessions-table"
import { UserFilter } from "@/components/user-filter"
import { UserMenu } from "@/components/user-menu"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AUTH_EXPIRED_EVENT,
  fetchDaily,
  fetchMe,
  fetchSummary,
  logout,
  UnauthorizedError,
  type DailyPoint,
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
const compactFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 })
const percentFormat = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 })

const chartConfig: ChartConfig = {
  input_tokens: { label: "Input tokens", color: "var(--chart-1)" },
  output_tokens: { label: "Output tokens", color: "var(--chart-2)" },
}

/**
 * Auth gate: load the current user, show the login screen if unauthenticated,
 * otherwise render the routed dashboard.
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

  // If any request 401s (e.g. the session token expired), drop back to login
  // instead of leaving screens showing an "unauthorized" error.
  useEffect(() => {
    const onExpired = () => setMe(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [])

  if (checking) {
    return <div className="flex min-h-svh items-center justify-center text-muted-foreground">Loading…</div>
  }
  if (!me) return <Login />

  return (
    <Routes>
      <Route element={<Layout me={me} />}>
        <Route index element={<Overview me={me} />} />
        <Route path="sessions" element={<SessionsTable />} />
        <Route path="keys" element={<ApiKeys />} />
      </Route>
    </Routes>
  )
}

const SCREEN_TITLES: Record<string, string> = {
  "/": "Overview",
  "/sessions": "Sessions",
  "/keys": "API keys",
}

/** App shell: sidebar + top bar; screens render into the <Outlet />. */
function Layout({ me }: { me: Me }) {
  const { pathname } = useLocation()
  const title = SCREEN_TITLES[pathname] ?? "Overview"

  async function handleLogout() {
    try {
      await logout()
    } catch {
      // ignore — reloading returns the user to the login screen anyway
    }
    window.location.reload()
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="h-svh min-w-0 overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="h-4" />
          <h1 className="font-heading text-sm font-semibold">{title}</h1>
          <div className="flex-1" />
          <ModeToggle />
          <UserMenu me={me} onLogout={handleLogout} />
        </header>
        {/* Content scrolls (styled ScrollArea), header stays fixed. The
            block! override stops Radix's display:table viewport wrapper from
            expanding horizontally so the layout width stays constrained. */}
        <ScrollArea className="min-h-0 flex-1 [&>[data-slot=scroll-area-viewport]>div]:block!">
          <main className="flex min-w-0 flex-col gap-6 p-6">
            <Outlet />
          </main>
        </ScrollArea>
      </SidebarInset>
    </SidebarProvider>
  )
}

const SCOPE_SUBTITLE = {
  org: "Usage across all users",
  account: "Usage across your Claude account",
  personal: "Your usage",
} as const

/** Overview screen: scope-aware KPIs, activity heatmap, and (for admins /
 *  account owners) per-user widgets plus a user filter. */
function Overview({ me }: { me: Me }) {
  const [allRows, setAllRows] = useState<UserSummary[]>([])
  const [daily, setDaily] = useState<DailyPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>("cost_usd")
  const [sortDesc, setSortDesc] = useState(true)
  const [selectedEmail, setSelectedEmail] = useState("")

  useEffect(() => {
    let cancelled = false
    fetchSummary()
      .then((data) => !cancelled && setAllRows(data))
      .catch((err: unknown) => {
        // An expired session is handled globally (back to login); don't flash an error.
        if (cancelled || err instanceof UnauthorizedError) return
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  // The heatmap is an aggregate, so it's filtered server-side by selected user.
  useEffect(() => {
    let cancelled = false
    fetchDaily(selectedEmail ? { email: selectedEmail } : {})
      .then((d) => !cancelled && setDaily(d))
      .catch(() => {
        /* heatmap is non-critical; ignore its errors */
      })
    return () => {
      cancelled = true
    }
  }, [selectedEmail])

  // Scope: admins see the org; a user who sees co-users owns an account;
  // otherwise it's a personal view of just their own usage.
  const scope: "org" | "account" | "personal" = me.is_admin
    ? "org"
    : allRows.some((r) => r.email !== me.email)
      ? "account"
      : "personal"

  const users = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.email))).sort(),
    [allRows]
  )

  // Everything below reflects the current filter (client-side narrowing).
  const rows = useMemo(
    () => (selectedEmail ? allRows.filter((r) => r.email === selectedEmail) : allRows),
    [allRows, selectedEmail]
  )

  const totals = useMemo(
    () =>
      rows.reduce(
        (acc, row) => ({
          sessions: acc.sessions + row.sessions,
          input_tokens: acc.input_tokens + row.input_tokens,
          output_tokens: acc.output_tokens + row.output_tokens,
          cache_read: acc.cache_read + row.cache_read,
          cache_write: acc.cache_write + row.cache_write,
          cost_usd: acc.cost_usd + row.cost_usd,
        }),
        { sessions: 0, input_tokens: 0, output_tokens: 0, cache_read: 0, cache_write: 0, cost_usd: 0 }
      ),
    [rows]
  )

  // Cache-hit ratio: cache reads vs. all input the model saw (input + cache read).
  // High = cheap/efficient reuse; low with many writes = wasteful.
  const cacheHitRatio = useMemo(() => {
    const denom = totals.input_tokens + totals.cache_read
    return denom > 0 ? totals.cache_read / denom : 0
  }, [totals])

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

  const isMultiUser = rows.length > 1
  const showFilter = scope !== "personal" && users.length > 1
  const kpiGrid = isMultiUser
    ? "grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6"
    : "grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5"

  return (
    <>
      {error && <p className="text-sm text-destructive">Could not load usage data: {error}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{SCOPE_SUBTITLE[scope]}</p>
        {showFilter && (
          <UserFilter users={users} value={selectedEmail} onChange={setSelectedEmail} />
        )}
      </div>

      <div className={kpiGrid}>
        {isMultiUser && (
          <StatCard icon={Users} label="Users" value={numberFormat.format(rows.length)} />
        )}
        <StatCard icon={Layers} label="Sessions" value={numberFormat.format(totals.sessions)} />
        <StatCard
          icon={Coins}
          label="Total tokens"
          value={compactFormat.format(totals.input_tokens + totals.output_tokens)}
          hint={`${compactFormat.format(totals.input_tokens)} in · ${compactFormat.format(totals.output_tokens)} out`}
        />
        <StatCard
          icon={Database}
          label="Cache read"
          value={compactFormat.format(totals.cache_read)}
          hint={`${compactFormat.format(totals.cache_write)} written`}
        />
        <StatCard icon={Gauge} label="Cache hit ratio" value={percentFormat.format(cacheHitRatio)} />
        <StatCard icon={CircleDollarSign} label="Cost" value={costFormat.format(totals.cost_usd)} />
      </div>

      <section>
        <h2 className="font-heading text-lg font-medium">Activity</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Daily token usage (input + output) over the last year — darker means a busier day.
        </p>
        <ActivityHeatmap data={daily} />
      </section>

      {isMultiUser && (
        <section>
          <h2 className="font-heading text-lg font-medium">Tokens by user</h2>
          <p className="mb-3 text-sm text-muted-foreground">Input vs. output tokens per user</p>
          <ChartContainer config={chartConfig} className="aspect-auto h-72 w-full">
            <BarChart data={rows} margin={{ left: 12, right: 12 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="email"
                tickLine={false}
                axisLine={false}
                tickFormatter={(email: string) => email.split("@")[0]}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={44}
                tickFormatter={(v: number) => compactFormat.format(v)}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="input_tokens" stackId="tokens" fill="var(--color-input_tokens)" maxBarSize={48} />
              <Bar dataKey="output_tokens" stackId="tokens" fill="var(--color-output_tokens)" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ChartContainer>
        </section>
      )}

      {scope !== "personal" && (
        <section>
          <h2 className="font-heading text-lg font-medium">Per-user summary</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            {loading ? "Loading…" : `${rows.length} user(s)`}
          </p>
          <ScrollArea className="w-full rounded-lg border border-border">
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
                  <TableCell className="text-muted-foreground">{row.account_email}</TableCell>
                  <TableCell>{numberFormat.format(row.sessions)}</TableCell>
                  <TableCell className="font-mono">{numberFormat.format(row.input_tokens)}</TableCell>
                  <TableCell className="font-mono">{numberFormat.format(row.output_tokens)}</TableCell>
                  <TableCell className="font-mono">{numberFormat.format(row.cache_read)}</TableCell>
                  <TableCell className="font-mono">{numberFormat.format(row.cache_write)}</TableCell>
                  <TableCell className="font-mono">{costFormat.format(row.cost_usd)}</TableCell>
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
          </ScrollArea>
        </section>
      )}
    </>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {label}
        </span>
        <Icon className="size-4 shrink-0 text-muted-foreground" />
      </div>
      <p className="truncate font-mono text-xl font-semibold tabular-nums" title={value}>
        {value}
      </p>
      <p className="truncate text-xs text-muted-foreground">{hint ?? " "}</p>
    </div>
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
        {isActive && (desc ? <ArrowDown className="size-3.5" /> : <ArrowUp className="size-3.5" />)}
      </span>
    </TableHead>
  )
}

export { App }
