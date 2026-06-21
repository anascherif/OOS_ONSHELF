"use client"

import { useEffect, useState, useCallback } from "react"
import { KpiBoard } from "@/components/kpi-board"
import { DepletionChart } from "@/components/depletion-chart"
import { AlertCenter } from "@/components/alert-center"
import { CalibrationPanel } from "@/components/calibration-panel"
import { FinancialImpact } from "@/components/financial-impact"
import {
  fetchLatestScan,
  fetchScanHistory,
  fetchAlertLog,
  fetchChannelStatus,
  fetchConfig,
  getStockState,
  STATE_META,
  type Scan,
  type AlertEvent,
  type ChannelStatus,
  type ShelfConfig,
} from "@/lib/inventory"
import { RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

const POLL_INTERVAL = 15000

export default function Page() {
  const [scans, setScans] = useState<Scan[]>([])
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [channels, setChannels] = useState<ChannelStatus[]>([])
  const [config, setConfig] = useState<ShelfConfig | null>(null)
  const [now, setNow] = useState<string>("")
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [s, a, ch, cfg] = await Promise.all([
        fetchScanHistory(),
        fetchAlertLog(),
        fetchChannelStatus(),
        fetchConfig(),
      ])
      setScans(s)
      setAlerts(a)
      setChannels(ch)
      if (cfg) setConfig(cfg)
      setError(null)
    } catch {
      setError("Cannot reach ShelfSense API on port 5001. Is the backend running?")
    }
  }, [])

  useEffect(() => {
    const clock = setInterval(
      () =>
        setNow(
          new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        ),
      1000,
    )
    load()
    const poll = setInterval(load, POLL_INTERVAL)
    return () => {
      clearInterval(clock)
      clearInterval(poll)
    }
  }, [load])

  const latest = scans.length > 0 ? scans[scans.length - 1] : null
  const state = latest ? getStockState(latest.stock) : "stocked"
  const meta = STATE_META[state]

  return (
    <main className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 md:px-6">
          <div className="flex items-center gap-3.5">
            <div className="group relative">
              <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-primary/20 to-primary/5 opacity-0 blur transition-opacity duration-500 group-hover:opacity-100" />
              <div className="relative flex size-11 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-card to-card/80 backdrop-blur-sm transition-all duration-300 group-hover:shadow-lg group-hover:shadow-primary/10 border border-primary/10">
                <img
                  src="/logo.png"
                  alt="ShelfSense logo"
                  className="size-7 object-contain transition-transform duration-300 group-hover:scale-110"
                  width={28}
                  height={28}
                />
              </div>
            </div>
            <div>
              <h1 className="text-sm font-semibold leading-tight md:text-base">ShelfSense</h1>
              <p className="text-xs text-muted-foreground">
                {config
                  ? `Calibrated on ${config.calibrated_on} | Alert < ${config.alert_threshold}%`
                  : "Real-Time Shelf Monitoring"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {latest && (
              <div
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium",
                  meta.tone,
                )}
              >
                <span
                  className={cn(
                    "size-2 rounded-full",
                    meta.dot,
                    state === "critical" && "animate-pulse",
                  )}
                />
                {meta.label} | {latest.stock}%
              </div>
            )}
            <div className="hidden items-center gap-1.5 font-mono text-xs text-muted-foreground sm:flex">
              <RefreshCw className="size-3.5 animate-spin [animation-duration:3s]" />
              {now}
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 md:px-6">
        {error && (
          <div className="rounded-lg border border-critical/30 bg-critical/5 px-4 py-3 text-sm text-critical">
            {error}
          </div>
        )}

        {latest ? (
          <>
            <KpiBoard latest={latest} scanCount={scans.length} config={config} />

            <FinancialImpact
              scans={scans}
              latest={latest}
              config={config}
            />

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <DepletionChart scans={scans} alertThreshold={config?.alert_threshold} />
              </div>
              <div className="lg:col-span-1">
                <AlertCenter alerts={alerts} channels={channels} />
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-lg border border-dashed border-border px-4 py-12 text-center text-sm text-muted-foreground">
            No scan data yet. Drop a photo into the <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">backend/incoming/</code> folder to start.
          </div>
        )}

        <CalibrationPanel config={config} />

        <footer className="pt-2 text-center text-xs text-muted-foreground">
          ShelfSense Retail Operations |{" "}
          {config ? `Scans every ${config.scan_interval_hours * 60} min` : "Auto-scan"} |{" "}
          {config
            ? `Alerts fire below ${config.alert_threshold}% capacity`
            : "Alerts on critical stock"}
        </footer>
      </div>
    </main>
  )
}
