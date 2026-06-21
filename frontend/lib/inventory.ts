export type StockState = "stocked" | "warning" | "critical"

export type Scan = {
  time: string
  timestamp: string
  stock: number
  exposedPixels: number
  productPixels: number
  missedUnits: number
  lostRevenue: number
  filename?: string
  status?: string
  dailyLossTnd?: number
  dailyMissedUnits?: number
  projectedLossTnd?: number
  recoverableTnd?: number
}

export type AlertEvent = {
  id: string
  time: string
  stock: number
  channels: ("Telegram" | "Gmail" | "WhatsApp")[]
  message: string
}

export type ChannelStatus = {
  name: string
  detail: string
  enabled: boolean
  last_sent: string | null
}

export type ShelfConfig = {
  roi: number[]
  shelf_dark_lower: number[] | null
  shelf_dark_upper: number[] | null
  shelf_light_lower: number[] | null
  shelf_light_upper: number[] | null
  yogurt_lower: number[] | null
  yogurt_upper: number[] | null
  ignore_lower: number[] | null
  ignore_upper: number[] | null
  exclude_regions: number[][]
  morph_kernel: number
  alert_threshold: number
  unit_price: number
  currency: string
  sales_per_hour: number
  scan_interval_hours: number
  store_open: number
  store_close: number
  roi_total_pixels: number
  calibrated_on: string
  image_size: number[]
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || ""

export async function fetchLatestScan(): Promise<Scan | null> {
  const res = await fetch(`${API_BASE}/api/latest-scan`)
  if (!res.ok) return null
  return res.json()
}

export async function fetchScanHistory(): Promise<Scan[]> {
  const res = await fetch(`${API_BASE}/api/scan-history`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchAlertLog(): Promise<AlertEvent[]> {
  const res = await fetch(`${API_BASE}/api/alert-log`)
  if (!res.ok) return []
  return res.json()
}

export async function fetchConfig(): Promise<ShelfConfig | null> {
  const res = await fetch(`${API_BASE}/api/config`)
  if (!res.ok) return null
  return res.json()
}

export async function fetchChannelStatus(): Promise<ChannelStatus[]> {
  const res = await fetch(`${API_BASE}/api/channel-status`)
  if (!res.ok) return []
  return res.json()
}

export function getStockState(stock: number): StockState {
  if (stock < 30) return "critical"
  if (stock < 50) return "warning"
  return "stocked"
}

export const STATE_META: Record<
  StockState,
  { label: string; tone: string; dot: string; text: string; ring: string }
> = {
  stocked: {
    label: "Fully Stocked",
    tone: "bg-success/10 text-success border-success/20",
    dot: "bg-success",
    text: "text-success",
    ring: "var(--success)",
  },
  warning: {
    label: "Reorder Warning",
    tone: "bg-warning/10 text-warning border-warning/20",
    dot: "bg-warning",
    text: "text-warning",
    ring: "var(--warning)",
  },
  critical: {
    label: "Critical Stock",
    tone: "bg-critical/10 text-critical border-critical/20",
    dot: "bg-critical",
    text: "text-critical",
    ring: "var(--critical)",
  },
}

export function formatMoney(n: number, currency = "TND"): string {
  return `${n.toFixed(2)} ${currency}`
}

export function formatPixels(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return `${n}`
}

export function sumFinancials(scans: Scan[]): { missedUnits: number; lostRevenue: number } {
  return scans.reduce(
    (acc, s) => ({
      missedUnits: acc.missedUnits + s.missedUnits,
      lostRevenue: acc.lostRevenue + s.lostRevenue,
    }),
    { missedUnits: 0, lostRevenue: 0 },
  )
}
