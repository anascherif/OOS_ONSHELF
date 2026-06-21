"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  ArrowLeft, ArrowRight, Check, Crop, Palette, Layers,
  Save, Upload, X, MousePointer2, Square, Eye
} from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL || ""

type Step = "upload" | "crop" | "uploaded" | "cropped" | "sampling" | "exclude" | "confirm"

type CalibState = {
  step: Step
  imagePath?: string
  imageSize?: [number, number]
  preview?: string
  cropPreview?: string
  roi?: [number, number, number, number]
  shelfDarkPoints: number[][]
  shelfDarkLower?: number[] | null
  shelfDarkUpper?: number[] | null
  shelfLightPoints: number[][]
  shelfLightLower?: number[] | null
  shelfLightUpper?: number[] | null
  yogurtPoints: number[][]
  yogurtLower?: number[] | null
  yogurtUpper?: number[] | null
  ignorePoints: number[][]
  ignoreLower?: number[] | null
  ignoreUpper?: number[] | null
  excludeRegions: number[][]
  maskPreview?: string
  stockEstimate?: number
}

type ColorMode = "dark" | "light" | "yogurt" | "ignore"

const COLOR_MODE_META: Record<ColorMode, { label: string; color: string }> = {
  dark: { label: "Dark Shelf", color: "#ffa500" },
  light: { label: "Light Shelf", color: "#ffff00" },
  yogurt: { label: "Yogurt (exclude)", color: "#ff0000" },
  ignore: { label: "Ignore Tags", color: "#ff7800" },
}

function Rect({
  x1, y1, x2, y2, color, label
}: {
  x1: number; y1: number; x2: number; y2: number
  color: string; label?: string
}) {
  const left = Math.min(x1, x2)
  const top = Math.min(y1, y2)
  const w = Math.abs(x2 - x1)
  const h = Math.abs(y2 - y1)
  return (
    <div
      className="absolute border-2 pointer-events-none"
      style={{ left, top, width: w, height: h, borderColor: color }}
    >
      {label && (
        <span
          className="absolute -top-4 left-0.5 text-[10px] font-mono whitespace-nowrap"
          style={{ color }}
        >
          {label}
        </span>
      )}
    </div>
  )
}

function ImageCanvas({
  src, width, height, children
}: {
  src: string; width: number; height: number; children?: React.ReactNode
}) {
  const maxDisplayW = 800
  const displayW = Math.min(width, maxDisplayW)
  const displayH = Math.round(height * (displayW / width))
  return (
    <div
      className="relative overflow-hidden rounded-lg border border-border bg-muted/30"
      style={{ width: displayW, height: displayH }}
    >
      <img
        src={`data:image/jpeg;base64,${src}`}
        alt="calibration"
        className="absolute inset-0 w-full h-full object-contain"
        draggable={false}
      />
      {children}
    </div>
  )
}

function getEventPos(
  e: React.MouseEvent<HTMLDivElement>,
  container: HTMLDivElement,
  imgW: number,
  imgH: number,
  maxDisplayW: number,
): { x: number; y: number } {
  const rect = container.getBoundingClientRect()
  const displayW = Math.min(imgW, maxDisplayW)
  const displayH = Math.round(imgH * (displayW / imgW))
  const offsetX = (rect.width - displayW) / 2
  const offsetY = (rect.height - displayH) / 2
  const px = e.clientX - rect.left - offsetX
  const py = e.clientY - rect.top - offsetY
  const scale = imgW / displayW
  return {
    x: Math.round(Math.max(0, Math.min(px * scale, imgW - 1))),
    y: Math.round(Math.max(0, Math.min(py * scale, imgH - 1))),
  }
}

export default function CalibratePage() {
  const [state, setState] = useState<CalibState>({
    step: "upload",
    shelfDarkPoints: [],
    shelfLightPoints: [],
    yogurtPoints: [],
    ignorePoints: [],
    excludeRegions: [],
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState<Step>("upload")
  const [colorMode, setColorMode] = useState<ColorMode>("dark")
  const containerRef = useRef<HTMLDivElement>(null)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [dragEnd, setDragEnd] = useState<{ x: number; y: number } | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const updateState = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/calibrate/state`)
      if (res.ok) {
        const data = await res.json()
        if (data.step) {
          setState(data)
          if (data.step === "uploaded") setCurrentStep("crop")
          else if (data.step === "cropped" || data.step === "sampling") setCurrentStep("sampling")
          else if (data.step === "exclude") setCurrentStep("exclude")
        }
      }
    } catch { }
  }, [])

  useEffect(() => { updateState() }, [updateState])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append("image", file)
      const res = await fetch(`${API}/api/calibrate/upload`, { method: "POST", body: fd })
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setState(s => ({ ...s, preview: data.preview, imageSize: [data.width, data.height], step: "uploaded" }))
      setCurrentStep("crop")
    } catch { setError("Upload failed") }
    finally { setLoading(false) }
  }

  const handleCropConfirm = async () => {
    if (!dragStart || !dragEnd) { setError("Draw a crop rectangle first"); return }
    const x1 = Math.min(dragStart.x, dragEnd.x)
    const y1 = Math.min(dragStart.y, dragEnd.y)
    const x2 = Math.max(dragStart.x, dragEnd.x)
    const y2 = Math.max(dragStart.y, dragEnd.y)
    if ((x2 - x1) < 10 || (y2 - y1) < 10) { setError("Crop too small"); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/calibrate/crop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roi: [y1, y2, x1, x2] }),
      })
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setState(s => ({ ...s, cropPreview: data.crop_preview, roi: data.roi, step: "cropped" }))
      setCurrentStep("sampling")
      setDragStart(null)
      setDragEnd(null)
    } catch { setError("Crop failed") }
    finally { setLoading(false) }
  }

  const handleColorClick = async (cx: number, cy: number) => {
    if (!state.roi) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/calibrate/color-sample`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: colorMode, x: cx, y: cy }),
      })
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setState(s => ({ ...s, maskPreview: data.maskPreview, stockEstimate: data.stockEstimate, step: "sampling" }))
    } catch { setError("Color sample failed") }
    finally { setLoading(false) }
  }

  const handleExcludeEnd = async () => {
    if (!dragStart || !dragEnd) return
    const x1 = Math.min(dragStart.x, dragEnd.x)
    const y1 = Math.min(dragStart.y, dragEnd.y)
    const x2 = Math.max(dragStart.x, dragEnd.x)
    const y2 = Math.max(dragStart.y, dragEnd.y)
    if ((x2 - x1) < 5 || (y2 - y1) < 5) { setDragStart(null); setDragEnd(null); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/calibrate/exclude`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x1, y1, x2, y2 }),
      })
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setState(s => ({ ...s, excludeRegions: data.exclude_regions }))
    } catch { setError("Failed to add exclusion") }
    finally { setLoading(false) }
    setDragStart(null)
    setDragEnd(null)
  }

  const handleExcludeClear = async () => {
    await fetch(`${API}/api/calibrate/exclude-clear`, { method: "POST" })
    setState(s => ({ ...s, excludeRegions: [] }))
  }

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/calibrate/save`, { method: "POST" })
      const data = await res.json()
      if (data.error) { setError(data.error); return }
      setCurrentStep("confirm")
    } catch { setError("Save failed") }
    finally { setLoading(false) }
  }

  const handleReset = async () => {
    await fetch(`${API}/api/calibrate/reset`, { method: "POST" })
    setState({
      step: "upload",
      shelfDarkPoints: [], shelfLightPoints: [],
      yogurtPoints: [], ignorePoints: [],
      excludeRegions: [],
    })
    setCurrentStep("upload")
    setError(null)
    setDragStart(null)
    setDragEnd(null)
  }

  const isCropStep = currentStep === "crop"
  const isSampling = currentStep === "sampling"
  const isExclude  = currentStep === "exclude"
  const showImage  = isCropStep || isSampling || isExclude
  const imgSrc     = isCropStep ? state.preview : state.cropPreview
  const imgW       = isCropStep ? (state.imageSize?.[0] ?? 800) : (state.roi ? (state.roi[2] - state.roi[0]) : 800)
  const imgH       = isCropStep ? (state.imageSize?.[1] ?? 600) : (state.roi ? (state.roi[3] - state.roi[1]) : 600)

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current || !showImage || loading) return
    const pos = getEventPos(e, containerRef.current, imgW, imgH, 800)
    if (isSampling) {
      handleColorClick(pos.x, pos.y)
      return
    }
    setIsDragging(true)
    setDragStart(pos)
    setDragEnd(pos)
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || !containerRef.current || !dragStart || loading) return
    const pos = getEventPos(e, containerRef.current, imgW, imgH, 800)
    setDragEnd(pos)
  }

  const handleMouseUp = () => {
    if (!isDragging) return
    setIsDragging(false)
    if (isExclude) {
      handleExcludeEnd()
    }
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="" className="size-8 object-contain" />
            <h1 className="text-sm font-semibold">ShelfSense Calibration Wizard</h1>
          </div>
          <div className="flex items-center gap-2">
            {currentStep !== "upload" && (
              <Button variant="ghost" size="xs" onClick={handleReset}>
                <X className="size-3" /> Reset
              </Button>
            )}
            <Badge variant="outline" className="text-[10px]">
              Step {"upload crop sampling exclude confirm".split(" ").indexOf(currentStep) + 1} of 5
            </Badge>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6 space-y-4">
        {error && (
          <div className="rounded-lg border border-critical/30 bg-critical/5 px-4 py-3 text-sm text-critical">
            {error}
          </div>
        )}

        {/* Step 1: Upload */}
        {currentStep === "upload" && (
          <Card className="p-8">
            <div className="flex flex-col items-center gap-6 text-center">
              <div className="rounded-full bg-primary/10 p-4">
                <Upload className="size-8 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Upload a Shelf Photo</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Take a photo of your shelf and upload it to begin calibration.
                  Use the same angle/distance for all future monitoring photos.
                </p>
              </div>
              <label className="cursor-pointer">
                <input type="file" accept="image/*" onChange={handleUpload} className="hidden" disabled={loading} />
                <Button disabled={loading}>
                  {loading ? "Uploading..." : "Choose Photo"}
                  <Upload className="size-4" />
                </Button>
              </label>
            </div>
          </Card>
        )}

        {/* Step 2: Crop */}
        {isCropStep && imgSrc && (
          <Card className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <Crop className="size-4 text-primary" />
              <h2 className="font-semibold">Step 1: Define Shelf Region</h2>
              <p className="text-sm text-muted-foreground ml-2">
                Click and drag to draw a box around the shelf area
              </p>
            </div>
            <div
              ref={containerRef}
              className="relative"
              style={{ cursor: loading ? "wait" : "crosshair" }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={() => { if (isDragging) { setIsDragging(false); setDragEnd(null) } }}
            >
              <ImageCanvas src={imgSrc} width={imgW} height={imgH}>
                {dragStart && dragEnd && (
                  <Rect
                    x1={Math.min(dragStart.x, dragEnd.x)}
                    y1={Math.min(dragStart.y, dragEnd.y)}
                    x2={Math.max(dragStart.x, dragEnd.x)}
                    y2={Math.max(dragStart.y, dragEnd.y)}
                    color="#00ff00"
                    label="ROI"
                  />
                )}
              </ImageCanvas>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button onClick={handleCropConfirm} disabled={loading || !dragStart || !dragEnd}>
                Confirm Crop <ArrowRight className="size-4" />
              </Button>
            </div>
          </Card>
        )}

        {/* Step 3: Color Sampling */}
        {isSampling && imgSrc && (
          <Card className="p-6">
            <div className="mb-4 flex items-center gap-2 flex-wrap">
              <Palette className="size-4 text-primary" />
              <h2 className="font-semibold">Step 2: Sample Shelf Colors</h2>
              <p className="text-sm text-muted-foreground ml-2">
                Click on shelf areas to sample HSV values
              </p>
            </div>

            <div className="mb-4 flex flex-wrap gap-2">
              {(Object.entries(COLOR_MODE_META) as [ColorMode, typeof COLOR_MODE_META[ColorMode]][]).map(([mode, meta]) => {
                const count = state[`${mode === "dark" || mode === "light" ? "shelf" : ""}${mode === "dark" || mode === "light" ? "_" : ""}${mode}Points` as keyof CalibState]
                return (
                  <Button
                    key={mode}
                    variant={colorMode === mode ? "default" : "outline"}
                    size="xs"
                    onClick={() => setColorMode(mode)}
                  >
                    <span className="size-2 rounded-full mr-1" style={{ backgroundColor: meta.color }} />
                    {meta.label}
                    <Badge variant="secondary" className="ml-1 text-[10px]">
                      {Array.isArray(count) ? count.length : 0}
                    </Badge>
                  </Button>
                )
              })}
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div
                ref={containerRef}
                className="relative"
                style={{ cursor: loading ? "wait" : "crosshair" }}
                onClick={(e) => {
                  if (!containerRef.current || loading) return
                  const pos = getEventPos(e, containerRef.current, imgW, imgH, 800)
                  handleColorClick(pos.x, pos.y)
                }}
              >
                <ImageCanvas src={imgSrc} width={imgW} height={imgH}>
                  {state.shelfDarkPoints.length > 0 && (
                    <div className="absolute top-2 left-2 text-[10px] font-mono text-[#ffa500]">
                      Dark: {state.shelfDarkLower?.[0] ?? "?"} {state.shelfDarkLower?.[1] ?? "?"} {state.shelfDarkLower?.[2] ?? "?"}
                      {" - "}
                      {state.shelfDarkUpper?.[0] ?? "?"} {state.shelfDarkUpper?.[1] ?? "?"} {state.shelfDarkUpper?.[2] ?? "?"}
                    </div>
                  )}
                </ImageCanvas>
              </div>

              <div>
                {state.maskPreview ? (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Eye className="size-3" /> Mask Preview
                    </p>
                    <div className="overflow-hidden rounded-lg border border-border">
                      <img
                        src={`data:image/jpeg;base64,${state.maskPreview}`}
                        alt="mask preview"
                        className="w-full object-contain"
                      />
                    </div>
                    {state.stockEstimate !== undefined && (
                      <p className="font-mono text-xs text-muted-foreground">
                        Estimated stock: <span className="text-primary font-semibold">{state.stockEstimate}%</span>
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                    Click the shelf image to sample colors. The mask preview will appear here.
                  </div>
                )}
              </div>
            </div>

            <div className="mt-4 flex justify-between">
              <Button variant="outline" onClick={() => setCurrentStep("crop")}>
                <ArrowLeft className="size-4" /> Back to Crop
              </Button>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={handleReset}>Reset All Points</Button>
                <Button onClick={() => setCurrentStep("exclude")} disabled={!state.shelfDarkLower && !state.shelfLightLower}>
                  Next: Exclusion <ArrowRight className="size-4" />
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* Step 4: Exclusion Regions */}
        {isExclude && imgSrc && (
          <Card className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <Layers className="size-4 text-primary" />
              <h2 className="font-semibold">Step 3: Mark Exclusion Regions</h2>
              <p className="text-sm text-muted-foreground ml-2">
                Draw rectangles over price tags / barcodes to ignore
              </p>
            </div>
            <div
              ref={containerRef}
              className="relative"
              style={{ cursor: loading ? "wait" : "crosshair" }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={() => { if (isDragging) { setIsDragging(false); setDragEnd(null) } }}
            >
              <ImageCanvas src={imgSrc} width={imgW} height={imgH}>
                {state.excludeRegions.map((r, i) => (
                  <Rect key={i} x1={r[2]} y1={r[0]} x2={r[3]} y2={r[1]} color="#ff6400" label={`X${i + 1}`} />
                ))}
                {dragStart && dragEnd && (
                  <Rect
                    x1={Math.min(dragStart.x, dragEnd.x)}
                    y1={Math.min(dragStart.y, dragEnd.y)}
                    x2={Math.max(dragStart.x, dragEnd.x)}
                    y2={Math.max(dragStart.y, dragEnd.y)}
                    color="#ffcc00"
                    label="new"
                  />
                )}
              </ImageCanvas>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <p className="text-xs text-muted-foreground">{state.excludeRegions.length} exclusion rectangle(s)</p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleExcludeClear} disabled={state.excludeRegions.length === 0}>
                  <X className="size-3" /> Clear
                </Button>
                <Button onClick={handleSave} disabled={loading}>
                  <Save className="size-4" /> Save Configuration
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* Step 5: Confirm */}
        {currentStep === "confirm" && (
          <Card className="p-8">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="rounded-full bg-success/10 p-4">
                <Check className="size-8 text-success" />
              </div>
              <h2 className="text-lg font-semibold">Calibration Saved!</h2>
              <p className="text-sm text-muted-foreground">
                <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">shelf_config.json</code> has been written.
                The watcher will use these settings for all future scans.
              </p>
              <div className="flex gap-3">
                <Button onClick={handleReset}>
                  Calibrate Again
                </Button>
                <Button variant="outline" onClick={() => window.location.href = "/"}>
                  <ArrowLeft className="size-4" /> Back to Dashboard
                </Button>
              </div>
            </div>
          </Card>
        )}
      </div>
    </main>
  )
}
