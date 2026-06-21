"use client"

import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ShelfConfig } from "@/lib/inventory"
import { SlidersHorizontal, Crop, Palette, Layers, Lock } from "lucide-react"

function FieldRow({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs tabular-nums text-foreground">
        {value !== null && value !== undefined ? String(value) : "--"}
      </span>
    </div>
  )
}

function HsvBlock({ title, lower, upper }: { title: string; lower: number[] | null; upper: number[] | null }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <div className="grid grid-cols-3 gap-1.5">
        {(["H", "S", "V"] as const).map((ch, i) => (
          <div key={ch} className="rounded border border-border bg-muted/30 px-2 py-1.5 text-center">
            <div className="text-[10px] text-muted-foreground">{ch}</div>
            <div className="font-mono text-xs tabular-nums text-foreground">
              {lower?.[i] ?? "--"} - {upper?.[i] ?? "--"}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CalibrationPanel({ config }: { config: ShelfConfig | null }) {
  if (!config) {
    return (
      <Card className="p-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <SlidersHorizontal className="size-4" />
          Calibration data unavailable. Run <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">hsv_calibrator.py</code> first.
        </div>
      </Card>
    )
  }

  const roi = config.roi ?? [0, 0, 0, 0]

  return (
    <Card className="p-6">
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <SlidersHorizontal className="size-4 text-primary" />
            CV Calibration Workspace
          </h2>
          <p className="text-sm text-muted-foreground">
            Inverse background masking parameters for the yogurt shelf ROI
          </p>
        </div>
        <Badge variant="secondary" className="gap-1">
          <Lock className="size-3" />
          Read-only
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* ROI */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Crop className="size-4 text-muted-foreground" />
            Region of Interest
          </div>
          <div className="grid grid-cols-2 gap-2">
            <FieldRow label="X" value={roi[0]} />
            <FieldRow label="Y" value={roi[1]} />
            <FieldRow label="Width" value={roi[2]} />
            <FieldRow label="Height" value={roi[3]} />
          </div>
          <div className="rounded-lg border border-dashed border-border p-3">
            <div className="relative aspect-video w-full overflow-hidden rounded bg-muted/40">
              <div
                className="absolute border-2 border-primary bg-primary/10"
                style={{ left: "16%", top: "14%", right: "12%", bottom: "18%" }}
              >
                <span className="absolute -top-5 left-0 font-mono text-[10px] text-primary">ROI</span>
              </div>
            </div>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              bbox = [{roi[0]}, {roi[1]}, {roi[2]}, {roi[3]}]
            </p>
          </div>
          {config.image_size && (
            <p className="text-[11px] text-muted-foreground">
              Source image: {config.image_size[0]}x{config.image_size[1]}
            </p>
          )}
        </div>

        {/* HSV ranges */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Palette className="size-4 text-muted-foreground" />
            HSV Color Ranges
          </div>
          <HsvBlock title="Shelf Dark (BG)" lower={config.shelf_dark_lower} upper={config.shelf_dark_upper} />
          <HsvBlock title="Shelf Light (BG)" lower={config.shelf_light_lower} upper={config.shelf_light_upper} />
          <HsvBlock title="Yogurt (Product)" lower={config.yogurt_lower} upper={config.yogurt_upper} />
          {config.ignore_lower && config.ignore_upper && (
            <HsvBlock title="Ignore Tag" lower={config.ignore_lower} upper={config.ignore_upper} />
          )}
        </div>

        {/* Morphology + Config */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Layers className="size-4 text-muted-foreground" />
            Morphology & Config
          </div>
          <FieldRow label="Kernel Size" value={`${config.morph_kernel}x${config.morph_kernel} px`} />
          <FieldRow label="Alert Threshold" value={`${config.alert_threshold}%`} />
          <FieldRow label="Exclude Regions" value={`${config.exclude_regions?.length ?? 0} rectangles`} />
          <div className="space-y-2 pt-2">
            <p className="text-xs font-medium text-muted-foreground">Financial Defaults</p>
            <FieldRow label="Unit Price" value={`${config.unit_price} ${config.currency}`} />
            <FieldRow label="Sales / Hour" value={config.sales_per_hour} />
            <FieldRow label="Scan Interval" value={`${config.scan_interval_hours * 60} min`} />
            <FieldRow label="Store Hours" value={`${config.store_open}:00 - ${config.store_close}:00`} />
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
            <div>kernel = np.ones(({config.morph_kernel},{config.morph_kernel}))</div>
            <div>cv2.morphologyEx(mask,</div>
            <div className="pl-3">OPEN, kernel)</div>
          </div>
          <p className="text-xs text-muted-foreground">
            To change values, run <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">hsv_calibrator.py</code> and recalibrate.
          </p>
        </div>
      </div>
    </Card>
  )
}
