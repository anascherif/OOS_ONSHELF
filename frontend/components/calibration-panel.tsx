"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { SlidersHorizontal, Crop, Palette, Layers } from "lucide-react"

type RangeRow = { label: string; key: string; value: number; min: number; max: number; unit?: string }

function Slider({ row, onChange }: { row: RangeRow; onChange: (v: number) => void }) {
  const pct = ((row.value - row.min) / (row.max - row.min)) * 100
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-xs text-muted-foreground">{row.label}</label>
        <span className="font-mono text-xs tabular-nums text-foreground">
          {row.value}
          {row.unit ?? ""}
        </span>
      </div>
      <input
        type="range"
        min={row.min}
        max={row.max}
        value={row.value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none [&::-webkit-slider-thumb]:size-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow"
        style={{
          background: `linear-gradient(to right, var(--primary) ${pct}%, var(--muted) ${pct}%)`,
        }}
      />
    </div>
  )
}

export function CalibrationPanel() {
  const [roi, setRoi] = useState({ x: 320, y: 140, w: 1280, h: 720 })
  const [hsv, setHsv] = useState({
    hLow: 95,
    hHigh: 130,
    sLow: 25,
    sHigh: 95,
    vLow: 60,
    vHigh: 200,
  })
  const [kernel, setKernel] = useState(5)
  const [iterations, setIterations] = useState(2)

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
        <span className="rounded-full bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground">
          Admin
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* ROI */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Crop className="size-4 text-muted-foreground" />
            Region of Interest
          </div>
          <div className="grid grid-cols-2 gap-2">
            {(["x", "y", "w", "h"] as const).map((k) => (
              <div key={k} className="rounded-lg border border-border bg-muted/30 p-2">
                <div className="text-[11px] uppercase text-muted-foreground">
                  {k === "w" ? "width" : k === "h" ? "height" : k}
                </div>
                <input
                  type="number"
                  value={roi[k]}
                  onChange={(e) => setRoi({ ...roi, [k]: Number(e.target.value) })}
                  className="w-full bg-transparent font-mono text-sm text-foreground outline-none"
                />
              </div>
            ))}
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
              bbox = [{roi.x}, {roi.y}, {roi.w}, {roi.h}]
            </p>
          </div>
        </div>

        {/* HSV */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Palette className="size-4 text-muted-foreground" />
            HSV Shelf Color Range
          </div>
          <div className="space-y-2.5">
            <Slider row={{ label: "Hue Low", key: "hLow", value: hsv.hLow, min: 0, max: 179 }} onChange={(v) => setHsv({ ...hsv, hLow: v })} />
            <Slider row={{ label: "Hue High", key: "hHigh", value: hsv.hHigh, min: 0, max: 179 }} onChange={(v) => setHsv({ ...hsv, hHigh: v })} />
            <Slider row={{ label: "Sat Low", key: "sLow", value: hsv.sLow, min: 0, max: 255 }} onChange={(v) => setHsv({ ...hsv, sLow: v })} />
            <Slider row={{ label: "Sat High", key: "sHigh", value: hsv.sHigh, min: 0, max: 255 }} onChange={(v) => setHsv({ ...hsv, sHigh: v })} />
            <Slider row={{ label: "Val Low", key: "vLow", value: hsv.vLow, min: 0, max: 255 }} onChange={(v) => setHsv({ ...hsv, vLow: v })} />
            <Slider row={{ label: "Val High", key: "vHigh", value: hsv.vHigh, min: 0, max: 255 }} onChange={(v) => setHsv({ ...hsv, vHigh: v })} />
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-2">
            <span className="text-[11px] text-muted-foreground">Preview</span>
            <span
              className="h-5 flex-1 rounded"
              style={{ background: `hsl(${(hsv.hLow + hsv.hHigh) * 1.0}, 45%, 55%)` }}
            />
          </div>
        </div>

        {/* Morphology */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Layers className="size-4 text-muted-foreground" />
            Morphological Cleanup
          </div>
          <Slider
            row={{ label: "Kernel Size", key: "kernel", value: kernel, min: 1, max: 15, unit: "px" }}
            onChange={setKernel}
          />
          <Slider
            row={{ label: "Iterations", key: "iter", value: iterations, min: 1, max: 8 }}
            onChange={setIterations}
          />
          <div className="grid grid-cols-3 gap-1.5">
            {Array.from({ length: 9 }).map((_, i) => {
              const k = Math.max(1, Math.min(2, kernel))
              const active = i === 4 || (kernel > 3 && [1, 3, 5, 7].includes(i)) || (kernel > 9 && true)
              return (
                <div
                  key={i}
                  className={cn(
                    "aspect-square rounded-sm border border-border transition-colors",
                    active ? "bg-primary/70" : "bg-muted/40",
                  )}
                />
              )
            })}
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
            <div>kernel = np.ones(({kernel},{kernel}))</div>
            <div>cv2.morphologyEx(mask,</div>
            <div className="pl-3">OPEN, kernel,</div>
            <div className="pl-3">iterations={iterations})</div>
          </div>
          <button className="w-full rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90">
            Apply &amp; Recalibrate
          </button>
        </div>
      </div>
    </Card>
  )
}
