"use client"

import { Card } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { CURRENCY, type Scan } from "@/lib/inventory"
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"
import { TrendingDown } from "lucide-react"

const chartConfig = {
  stock: { label: "Stock Level", color: "var(--chart-1)" },
} satisfies ChartConfig

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as Scan
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-lg">
      <div className="font-mono text-muted-foreground">{d.time}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-foreground">{d.stock}% remaining</div>
      <div className="text-muted-foreground">{d.exposedPixels.toLocaleString()}px exposed</div>
      <div className="mt-1 flex items-center gap-1 border-t border-border pt-1 font-mono text-critical">
        - {d.lostRevenue.toFixed(2)} {CURRENCY} lost
      </div>
    </div>
  )
}

export function DepletionChart({ scans }: { scans: Scan[] }) {
  return (
    <Card className="p-6">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <TrendingDown className="size-4 text-primary" />
            Historical Depletion
          </h2>
          <p className="text-sm text-muted-foreground">Chronological stock level across today&apos;s 15-min scans</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-3 rounded-sm bg-primary" /> Stock %
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-3 border-t-2 border-dashed border-critical" /> Threshold
          </span>
        </div>
      </div>

      <ChartContainer config={chartConfig} className="h-[280px] w-full">
        <AreaChart data={scans} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="fillStock" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--color-stock)" stopOpacity={0.4} />
              <stop offset="95%" stopColor="var(--color-stock)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="time"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={40}
            className="text-xs"
          />
          <YAxis
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            tickFormatter={(v) => `${v}%`}
            className="text-xs"
          />
          <ChartTooltip content={<CustomTooltip />} />
          <ReferenceLine
            y={30}
            stroke="var(--critical)"
            strokeDasharray="4 4"
            strokeWidth={1.5}
          />
          <Area
            dataKey="stock"
            type="monotone"
            stroke="var(--color-stock)"
            strokeWidth={2}
            fill="url(#fillStock)"
            dot={false}
            activeDot={{ r: 4, fill: "var(--color-stock)" }}
          />
        </AreaChart>
      </ChartContainer>
    </Card>
  )
}
