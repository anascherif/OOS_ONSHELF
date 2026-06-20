"use client"

import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { STATE_META, formatPixels, getStockState, ROI_TOTAL_PIXELS, type Scan } from "@/lib/inventory"
import { Activity, Boxes, Clock, ScanLine } from "lucide-react"

function StockGauge({ stock }: { stock: number }) {
  const state = getStockState(stock)
  const meta = STATE_META[state]
  const radius = 52
  const circumference = 2 * Math.PI * radius
  const dash = (stock / 100) * circumference

  return (
    <div className="relative flex size-[140px] items-center justify-center">
      <svg viewBox="0 0 140 140" className="size-full -rotate-90">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="var(--muted)" strokeWidth="10" />
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke={meta.ring}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-3xl font-semibold tabular-nums">{stock}</span>
        <span className="text-xs text-muted-foreground">% capacity</span>
      </div>
    </div>
  )
}

export function KpiBoard({ latest, scanCount }: { latest: Scan; scanCount: number }) {
  const state = getStockState(latest.stock)
  const meta = STATE_META[state]
  const exposedPct = Math.round((latest.exposedPixels / ROI_TOTAL_PIXELS) * 100)

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      {/* Capacity gauge */}
      <Card className="flex flex-col items-center justify-center gap-2 p-6">
        <div className="flex w-full items-center gap-2 text-xs font-medium text-muted-foreground">
          <Activity className="size-4" />
          Current Stock Capacity
        </div>
        <StockGauge stock={latest.stock} />
      </Card>

      {/* Status indicator */}
      <Card className="flex flex-col justify-between p-6">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Boxes className="size-4" />
          Product Status
        </div>
        <div className="space-y-3">
          <div className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold", meta.tone)}>
            <span className={cn("size-2 rounded-full", meta.dot, state === "critical" && "animate-pulse")} />
            {state === "critical" ? "🚨 " : ""}
            {meta.label}
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {state === "critical"
              ? "Stock below 30% threshold. Alert sequence active."
              : state === "warning"
                ? "Approaching reorder point. Monitoring closely."
                : "Shelf is well stocked. No action required."}
          </p>
        </div>
      </Card>

      {/* Pixel area */}
      <Card className="flex flex-col justify-between p-6">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <ScanLine className="size-4" />
          Pixel Area Analysis
        </div>
        <div className="space-y-3">
          <div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-muted-foreground">Tracked ROI</span>
              <span className="font-mono text-sm tabular-nums">{formatPixels(ROI_TOTAL_PIXELS)}px</span>
            </div>
            <div className="mt-1 flex h-2.5 overflow-hidden rounded-full bg-muted">
              <div
                className="bg-primary transition-all duration-700"
                style={{ width: `${100 - exposedPct}%` }}
              />
              <div className="bg-critical/70 transition-all duration-700" style={{ width: `${exposedPct}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-md bg-muted/50 p-2">
              <div className="text-muted-foreground">Product</div>
              <div className="font-mono text-sm text-primary">{formatPixels(latest.productPixels)}px</div>
            </div>
            <div className="rounded-md bg-muted/50 p-2">
              <div className="text-muted-foreground">Exposed BG</div>
              <div className="font-mono text-sm text-critical">{formatPixels(latest.exposedPixels)}px</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Last scan */}
      <Card className="flex flex-col justify-between p-6">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Clock className="size-4" />
          Last Scan
        </div>
        <div className="space-y-1">
          <div className="font-mono text-3xl font-semibold tabular-nums">{latest.time}</div>
          <p className="text-sm text-muted-foreground">{`Scan #${scanCount} of today's sequence`}</p>
          <div className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2 py-1 text-xs font-medium text-success">
            <span className="size-1.5 animate-pulse rounded-full bg-success" />
            Next scan in 15 min
          </div>
        </div>
      </Card>
    </div>
  )
}
