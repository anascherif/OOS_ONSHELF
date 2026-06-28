"use client"

/*
  Financial impact card — shows the revenue consequences of empty shelf space.
  3 columns: daily lost revenue, missed unit sales, current scan loss.

  The 'recoverable' estimate at the bottom assumes that restocking now
  stops the loss for the remaining intervals before store close.
  This is a rough model — adjust constants in shelf_config.json.
*/

import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { formatMoney, sumFinancials, type Scan, type ShelfConfig } from "@/lib/inventory"
import { TrendingDown, PackageX, CircleDollarSign, ArrowDownRight } from "lucide-react"

export function FinancialImpact({
  scans,
  latest,
  config,
}: {
  scans: Scan[]
  latest: Scan
  config: ShelfConfig | null
}) {
  const currency = config?.currency ?? "TND"
  const unitPrice = config?.unit_price ?? 0.5
  const { missedUnits, lostRevenue } = sumFinancials(scans)
  const intervalLoss = latest.lostRevenue
  const intervalUnits = latest.missedUnits
  const dailyLoss = latest.dailyLossTnd ?? lostRevenue
  const dailyMissed = latest.dailyMissedUnits ?? missedUnits
  const projectedLoss = latest.projectedLossTnd ?? 0
  const recoverable = latest.recoverableTnd ?? 0
  const remainingIntervals = config
    ? Math.max(0, Math.round((config.store_close - config.store_open) / config.scan_interval_hours) - scans.length)
    : 0

  return (
    <Card className="overflow-hidden border-critical/25 bg-gradient-to-br from-critical/[0.07] to-transparent p-0">
      <div className="flex flex-col gap-1 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-critical/15 text-critical">
            <CircleDollarSign className="size-4.5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold leading-tight">Retail Opportunity Recovery</h2>
            <p className="text-xs text-muted-foreground">Empty shelf space translated into lost revenue</p>
          </div>
        </div>
        <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-critical/10 px-2.5 py-1 text-xs font-medium text-critical">
          <TrendingDown className="size-3.5" />
          Revenue at risk
        </span>
      </div>

      <div className="grid grid-cols-1 divide-y divide-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="flex flex-col justify-between gap-3 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <CircleDollarSign className="size-4" />
            Daily Lost Revenue
          </div>
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-3xl font-semibold tabular-nums text-critical">
                {dailyLoss.toFixed(2)}
              </span>
              <span className="text-sm font-medium text-critical/80">{currency}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Left on the table today |
              {projectedLoss > 0 ? ` ~${formatMoney(projectedLoss, currency)} projected by close` : " no projection yet"}
            </p>
          </div>
        </div>

        <div className="flex flex-col justify-between gap-3 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <PackageX className="size-4" />
            Missed Unit Sales
          </div>
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-3xl font-semibold tabular-nums text-foreground">
                {Math.round(dailyMissed)}
              </span>
              <span className="text-sm font-medium text-muted-foreground">units</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Products shoppers could not buy | {formatMoney(unitPrice, currency)}/unit
            </p>
          </div>
        </div>

        <div className="flex flex-col justify-between gap-3 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <ArrowDownRight className="size-4" />
            Current Scan Loss
          </div>
          <div>
            <div
              className={cn(
                "flex items-baseline gap-1.5",
                intervalLoss > 0.4 ? "text-critical" : intervalLoss > 0.15 ? "text-warning" : "text-success",
              )}
            >
              <span className="font-mono text-3xl font-semibold tabular-nums">- {intervalLoss.toFixed(2)}</span>
              <span className="text-sm font-medium opacity-80">{currency}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              This scan interval | {intervalUnits.toFixed(1)} units missed
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border bg-muted/30 px-5 py-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Action:</span> Every minute this shelf stays empty during
          peak hours compounds the loss. Restocking now recovers an estimated{" "}
          <span className="font-medium text-primary">
            {formatMoney(recoverable > 0 ? recoverable : intervalLoss * remainingIntervals, currency)}
          </span>{" "}
          before store close.
        </p>
      </div>
    </Card>
  )
}
