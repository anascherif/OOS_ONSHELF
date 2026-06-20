"use client"

import { useEffect, useMemo, useState } from "react"
import { KpiBoard } from "@/components/kpi-board"
import { DepletionChart } from "@/components/depletion-chart"
import { AlertCenter } from "@/components/alert-center"
import { CalibrationPanel } from "@/components/calibration-panel"
import { FinancialImpact } from "@/components/financial-impact"
import { buildAlertLog, generateDaySchedule, getStockState, STATE_META } from "@/lib/inventory"
import { RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

export default function Page() {
  const allScans = useMemo(() => generateDaySchedule(), [])
  // start partway through the day so there's history + an active state
  const [visibleCount, setVisibleCount] = useState(28)
  const [now, setNow] = useState<string>("")

  useEffect(() => {
    const update = () =>
      setNow(new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
    update()
    const clock = setInterval(update, 1000)
    // advance the simulated scan feed every 4s
    const feed = setInterval(() => {
      setVisibleCount((c) => (c >= allScans.length ? 28 : c + 1))
    }, 4000)
    return () => {
      clearInterval(clock)
      clearInterval(feed)
    }
  }, [allScans.length])

  const scans = allScans.slice(0, visibleCount)
  const latest = scans[scans.length - 1]
  const alerts = buildAlertLog(scans)
  const state = getStockState(latest.stock)
  const meta = STATE_META[state]

  return (
    <main className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 md:px-6">
          <div className="flex items-center gap-3.5">
            <div className="group relative">
              {/* Animated gradient border backdrop */}
              <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-primary/20 to-primary/5 opacity-0 blur transition-opacity duration-500 group-hover:opacity-100" />
              {/* Main logo container with smooth glass morphism */}
              <div className="relative flex size-11 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-card to-card/80 backdrop-blur-sm transition-all duration-300 group-hover:shadow-lg group-hover:shadow-primary/10 border border-primary/10">
                <img
                  src="/logo.png"
                  alt="Company logo"
                  className="size-7 object-contain transition-transform duration-300 group-hover:scale-110"
                  width={28}
                  height={28}
                />
              </div>
            </div>
            <div>
              <h1 className="text-sm font-semibold leading-tight md:text-base">ShelfSense</h1>
              <p className="text-xs text-muted-foreground">Yogurt Aisle · Camera 04 · Inverse BG Masking</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium",
                meta.tone,
              )}
            >
              <span className={cn("size-2 rounded-full", meta.dot, state === "critical" && "animate-pulse")} />
              {meta.label} · {latest.stock}%
            </div>
            <div className="hidden items-center gap-1.5 font-mono text-xs text-muted-foreground sm:flex">
              <RefreshCw className="size-3.5 animate-spin [animation-duration:3s]" />
              {now}
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 md:px-6">
        <KpiBoard latest={latest} scanCount={visibleCount} />

        <FinancialImpact scans={scans} latest={latest} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <DepletionChart scans={scans} />
          </div>
          <div className="lg:col-span-1">
            <AlertCenter alerts={alerts} />
          </div>
        </div>

        <CalibrationPanel />

        <footer className="pt-2 text-center text-xs text-muted-foreground">
          ShelfSense Retail Operations · Scans every 15 min · Alerts fire below 30% capacity
        </footer>
      </div>
    </main>
  )
}
