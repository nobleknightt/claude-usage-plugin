import { useMemo } from "react"

import { ScrollArea } from "@/components/ui/scroll-area"
import type { DailyPoint } from "@/lib/api"

const WEEKS = 53
const DAY_MS = 86_400_000
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const numberFormat = new Intl.NumberFormat("en-US")

type Cell = { key: string; date: Date; tokens: number; level: number }

function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** GitHub-style calendar of daily token activity over the last ~52 weeks. */
export function ActivityHeatmap({ data }: { data: DailyPoint[] }) {
  const weeks = useMemo(() => {
    const byDate = new Map(data.map((d) => [d.date, d.tokens]))
    const max = data.reduce((m, d) => Math.max(m, d.tokens), 0)

    const today = new Date()
    today.setHours(0, 0, 0, 0)
    // Start WEEKS weeks back, then rewind to that week's Sunday so columns align.
    const start = new Date(today.getTime() - (WEEKS * 7 - 1) * DAY_MS)
    start.setDate(start.getDate() - start.getDay())

    const cells: Cell[] = []
    for (let t = start.getTime(); t <= today.getTime(); t += DAY_MS) {
      const date = new Date(t)
      const tokens = byDate.get(isoDay(date)) ?? 0
      const level = tokens === 0 ? 0 : Math.min(4, Math.ceil((tokens / max) * 4))
      cells.push({ key: isoDay(date), date, tokens, level })
    }

    const weeks: Cell[][] = []
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
    return weeks
  }, [data])

  const levelColor = (level: number): string =>
    level === 0 ? "var(--muted)" : "var(--chart-1)"
  const levelOpacity = (level: number): number =>
    level === 0 ? 1 : [0.3, 0.5, 0.75, 1][level - 1]

  return (
    <div className="flex flex-col gap-2">
      <ScrollArea className="w-full">
        <div className="flex w-max gap-2 pb-3">
        {/* weekday labels */}
        <div className="mt-4 flex flex-col justify-between text-[10px] text-muted-foreground">
          <span>Mon</span>
          <span>Wed</span>
          <span>Fri</span>
        </div>
        <div className="flex flex-col gap-1">
          {/* month labels */}
          <div className="flex gap-1">
            {weeks.map((week, i) => {
              const first = week[0]
              const prev = weeks[i - 1]?.[0]
              const showMonth = first && (!prev || prev.date.getMonth() !== first.date.getMonth())
              return (
                <div key={i} className="w-3 text-[10px] text-muted-foreground">
                  {showMonth ? MONTHS[first.date.getMonth()] : ""}
                </div>
              )
            })}
          </div>
          {/* the grid: columns = weeks, rows = days */}
          <div className="flex gap-1">
            {weeks.map((week, i) => (
              <div key={i} className="flex flex-col gap-1">
                {week.map((cell) => (
                  <div
                    key={cell.key}
                    title={`${cell.key}: ${numberFormat.format(cell.tokens)} tokens`}
                    className="size-3 rounded-[3px] ring-1 ring-foreground/5"
                    style={{ backgroundColor: levelColor(cell.level), opacity: levelOpacity(cell.level) }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
        </div>
      </ScrollArea>

      {/* legend */}
      <div className="flex items-center gap-1.5 self-end text-[10px] text-muted-foreground">
        <span>Less</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <div
            key={level}
            className="size-3 rounded-[3px] ring-1 ring-foreground/5"
            style={{ backgroundColor: levelColor(level), opacity: levelOpacity(level) }}
          />
        ))}
        <span>More</span>
      </div>
    </div>
  )
}
