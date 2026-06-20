"use client"

import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { CURRENCY, UNIT_PRICE, formatMoney, sumFinancials, type Scan } from "@/lib/inventory"
import { TrendingDown, PackageX, CircleDollarSign, ArrowDownRight } from "lucide-react"

export function FinancialImpact({ scans, latest }: { scans: Scan[]; latest: Scan }) {
  const { missedUnits, lostRevenue } = sumFinancials(scans)
  const intervalLoss = latest.lostRevenue
  const intervalUnits = latest.missedUnits
  // projected end-of-day loss if the current interval's rate held for the rest of the day
  const remainingIntervals = Math.max(0, 48 - scans.length)
  const projectedLoss = lostRevenue + intervalLoss * remainingIntervals

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
        {/* Daily lost revenue — hero metric */}
        <div className="flex flex-col justify-between gap-3 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <CircleDollarSign className="size-4" />
            Daily Lost Revenue
          </div>
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-3xl font-semibold tabular-nums text-critical">
                {lostRevenue.toFixed(2)}
              </span>
              <span className="text-sm font-medium text-critical/80">{CURRENCY}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {"Left on the table today · ~"}
              {formatMoney(projectedLoss)} projected by close
            </p>
          </div>
        </div>

        {/* Missed unit sales */}
        <div className="flex flex-col justify-between gap-3 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <PackageX className="size-4" />
            Missed Unit Sales
          </div>
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-3xl font-semibold tabular-nums text-foreground">
                {Math.round(missedUnits)}
              </span>
              <span className="text-sm font-medium text-muted-foreground">units</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {"Products shoppers couldn't buy · "}
              {formatMoney(UNIT_PRICE)}/unit
            </p>
          </div>
        </div>

        {/* Current scan loss — micro metric */}
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
              <span className="text-sm font-medium opacity-80">{CURRENCY}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {"This 15-min interval · "}
              {intervalUnits.toFixed(1)} units missed
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border bg-muted/30 px-5 py-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Action:</span> Every minute this shelf stays empty during
          peak hours compounds the loss. Restocking now recovers an estimated{" "}
          <span className="font-medium text-primary">{formatMoney(intervalLoss * remainingIntervals)}</span> before
          store close.
        </p>
      </div>
    </Card>
  )
}
