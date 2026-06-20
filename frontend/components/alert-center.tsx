"use client"

import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { AlertEvent } from "@/lib/inventory"
import { Mail, MessageCircle, Send, BellRing } from "lucide-react"

type Channel = {
  name: string
  detail: string
  icon: typeof Mail
  status: "online" | "degraded"
  latency: string
}

const CHANNELS: Channel[] = [
  { name: "Telegram Bot API", detail: "@shelfsense_bot", icon: Send, status: "online", latency: "82ms" },
  { name: "Gmail SMTP Server", detail: "smtp.gmail.com:587", icon: Mail, status: "online", latency: "210ms" },
  { name: "WhatsApp Gateway", detail: "Cloud API v19.0", icon: MessageCircle, status: "degraded", latency: "640ms" },
]

const channelIcon: Record<string, typeof Mail> = {
  Telegram: Send,
  Gmail: Mail,
  WhatsApp: MessageCircle,
}

export function AlertCenter({ alerts }: { alerts: AlertEvent[] }) {
  return (
    <Card className="flex flex-col p-6">
      <div className="mb-4">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <BellRing className="size-4 text-primary" />
          Multi-Channel Alerts
        </h2>
        <p className="text-sm text-muted-foreground">Integration health &amp; dispatched alarm log</p>
      </div>

      {/* Channel health */}
      <div className="space-y-2">
        {CHANNELS.map((c) => {
          const Icon = c.icon
          const online = c.status === "online"
          return (
            <div
              key={c.name}
              className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2.5"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-md bg-muted">
                  <Icon className="size-4 text-foreground" />
                </div>
                <div>
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="font-mono text-xs text-muted-foreground">{c.detail}</div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
                    online ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                  )}
                >
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      online ? "bg-success" : "bg-warning animate-pulse",
                    )}
                  />
                  {online ? "Online" : "Degraded"}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">{c.latency}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Audit log */}
      <div className="mt-5 flex min-h-0 flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Critical Alert Log
          </span>
          <span className="font-mono text-xs text-muted-foreground">{alerts.length} events</span>
        </div>
        <div className="-mr-2 flex-1 space-y-2 overflow-y-auto pr-2">
          {alerts.length === 0 && (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
              No critical alarms dispatched today.
            </p>
          )}
          {alerts.map((a) => (
            <div key={a.id} className="rounded-lg border border-critical/20 bg-critical/5 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-medium text-critical">{a.time}</span>
                <span className="rounded bg-critical/15 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-critical">
                  {a.stock}%
                </span>
              </div>
              <p className="mt-1 text-sm text-foreground">🚨 {a.message}</p>
              <div className="mt-1.5 flex items-center gap-1.5">
                {a.channels.map((ch) => {
                  const Icon = channelIcon[ch]
                  return (
                    <span
                      key={ch}
                      className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                    >
                      <Icon className="size-3" />
                      {ch}
                    </span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
