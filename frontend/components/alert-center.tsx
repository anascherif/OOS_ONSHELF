"use client"

import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { type AlertEvent, type ChannelStatus } from "@/lib/inventory"
import { Bell, CheckCircle2, XCircle } from "lucide-react"

function ChannelPill({ ch }: { ch: ChannelStatus }) {
  return (
    <div className="flex items-center justify-between rounded-lg border bg-card px-3 py-2.5">
      <div className="flex items-center gap-2.5">
        <span className={cn("size-2.5 rounded-full transition-colors", ch.enabled ? "bg-success" : "bg-muted-foreground/30")} />
        <div>
          <div className="text-sm font-medium leading-tight">{ch.name}</div>
          <div className="text-xs text-muted-foreground">{ch.detail}</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {ch.enabled ? (
          <Badge variant="default" className="bg-success/15 text-success hover:bg-success/20 border-success/20">
            <CheckCircle2 className="mr-1 size-3" /> Active
          </Badge>
        ) : (
          <Badge variant="secondary" className="text-muted-foreground">
            <XCircle className="mr-1 size-3" /> Off
          </Badge>
        )}
      </div>
    </div>
  )
}

export function AlertCenter({
  alerts,
  channels,
}: {
  alerts: AlertEvent[]
  channels: ChannelStatus[]
}) {
  return (
    <Card className="flex flex-col p-0">
      <div className="flex items-center gap-2 border-b border-border px-5 py-4">
        <Bell className="size-4 text-primary" />
        <h2 className="text-sm font-semibold">Alert Center</h2>
        {alerts.length > 0 && (
          <Badge variant="destructive" className="ml-auto text-xs">
            {alerts.length}
          </Badge>
        )}
      </div>

      {/* Channel status */}
      <div className="space-y-2 border-b border-border px-5 py-4">
        <p className="text-xs font-medium text-muted-foreground mb-2">Channel Status</p>
        {channels.length === 0 ? (
          <p className="text-xs text-muted-foreground">No channel config available.</p>
        ) : (
          channels.map((ch) => <ChannelPill key={ch.name} ch={ch} />)
        )}
      </div>

      {/* Alert log */}
      <div className="px-5 py-4">
        <p className="text-xs font-medium text-muted-foreground mb-2">Alert Log</p>
        {alerts.length === 0 ? (
          <p className="text-xs text-muted-foreground">No alerts triggered yet.</p>
        ) : (
          <div className="space-y-2 max-h-[320px] overflow-y-auto">
            {alerts.map((a) => (
              <div
                key={a.id}
                className="rounded-lg border border-critical/20 bg-critical/5 px-3 py-2.5"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">{a.time}</span>
                  <span className="font-mono text-sm font-semibold text-critical">{a.stock}%</span>
                </div>
                <p className="mt-1 text-xs text-foreground leading-relaxed">{a.message}</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {a.channels.map((c) => (
                    <Badge key={c} variant="outline" className="text-xs border-critical/30 text-critical/80">
                      {c}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
