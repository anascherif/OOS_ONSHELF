export type StockState = "stocked" | "warning" | "critical"

export const ROI_TOTAL_PIXELS = 921_600 // 1280 x 720 ROI bounding box area

/** Retail Opportunity Recovery model constants */
export const CURRENCY = "TND"
/** average sale price of one unit on this shelf */
export const UNIT_PRICE = 3.2
/** units a fully-stocked shelf would sell during one 15-min interval at peak */
export const BASE_DEMAND_PER_INTERVAL = 1.7

export type Scan = {
  /** minutes since midnight for the scan */
  time: string
  timestamp: Date
  /** remaining stock percentage 0-100 */
  stock: number
  /** exposed empty-shelf background pixels */
  exposedPixels: number
  /** estimated product pixels */
  productPixels: number
  /** estimated units that could not be sold during this interval */
  missedUnits: number
  /** revenue lost during this interval (TND) */
  lostRevenue: number
}

/**
 * Translates an empty-shelf fraction into lost sales for a single 15-min
 * interval. Demand peaks during the 17:00-19:00 rush, and the share of
 * shoppers who walk away grows with how empty the shelf looks.
 */
export function computeScanLoss(stock: number, hour: number): { missedUnits: number; lostRevenue: number } {
  const emptyFraction = (100 - stock) / 100
  const rushMultiplier = hour >= 17 && hour <= 19 ? 1.8 : 1
  const missedUnits = BASE_DEMAND_PER_INTERVAL * emptyFraction * rushMultiplier
  return { missedUnits, lostRevenue: missedUnits * UNIT_PRICE }
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

export function formatMoney(n: number): string {
  return `${n.toFixed(2)} ${CURRENCY}`
}

export type AlertEvent = {
  id: string
  time: string
  stock: number
  channels: ("Telegram" | "Gmail" | "WhatsApp")[]
  message: string
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

/**
 * Simulates a full day of 15-minute scans where shoppers gradually
 * deplete the yogurt shelf, with an occasional restock bump.
 */
export function generateDaySchedule(): Scan[] {
  // deterministic seeded PRNG so SSR and client render identical data
  let seed = 1337
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296
    return seed / 4294967296
  }

  const scans: Scan[] = []
  const start = new Date()
  start.setHours(8, 0, 0, 0)

  let stock = 100
  // 8:00 -> ~20:00 => 48 scans (15 min each)
  for (let i = 0; i < 49; i++) {
    const ts = new Date(start.getTime() + i * 15 * 60 * 1000)
    // restock event mid-afternoon
    if (i === 30) stock = Math.min(100, stock + 55)
    else {
      const drop = 1.4 + rand() * 3.6
      const rushHour = ts.getHours() >= 17 && ts.getHours() <= 19 ? 2.2 : 1
      stock = Math.max(6, stock - drop * rushHour)
    }
    const rounded = Math.round(stock)
    const productPixels = Math.round((rounded / 100) * ROI_TOTAL_PIXELS)
    const { missedUnits, lostRevenue } = computeScanLoss(rounded, ts.getHours())
    scans.push({
      time: ts.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }),
      timestamp: ts,
      stock: rounded,
      productPixels,
      exposedPixels: ROI_TOTAL_PIXELS - productPixels,
      missedUnits,
      lostRevenue,
    })
  }
  return scans
}

export function buildAlertLog(scans: Scan[]): AlertEvent[] {
  const alerts: AlertEvent[] = []
  let prevCritical = false
  for (const s of scans) {
    const isCritical = s.stock < 30
    if (isCritical && !prevCritical) {
      alerts.push({
        id: `${s.time}-${s.stock}`,
        time: s.time,
        stock: s.stock,
        channels: s.stock < 20 ? ["Telegram", "Gmail", "WhatsApp"] : ["Telegram", "Gmail"],
        message: `Critical Stock Alert (${s.stock}%) dispatched`,
      })
    }
    prevCritical = isCritical
  }
  return alerts.reverse()
}

export function formatPixels(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return `${n}`
}
