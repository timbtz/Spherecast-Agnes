import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { TrendingDown, TrendingUp, X, Bell } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { PriceAlert } from "@/types/agnes";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES = {
  critical: "bg-red-500/10 border-red-500/30 text-red-500",
  warning: "bg-amber-500/10 border-amber-500/30 text-amber-500",
  info: "bg-blue-500/10 border-blue-500/30 text-blue-500",
};

export function AlertsView() {
  const qc = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["price-alerts", showDismissed],
    queryFn: () => agnesApi.listAlerts(showDismissed),
  });

  const dismissMutation = useMutation({
    mutationFn: (id: number) => agnesApi.dismissAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["price-alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-count"] });
    },
  });

  if (isLoading) return <LoadingState label="Loading alerts…" />;
  if (error) return <ErrorState message="Failed to load price alerts." />;
  if (!data?.alerts?.length) {
    return (
      <EmptyState
        icon={<Bell className="size-4" />}
        title="No price alerts"
        body={showDismissed ? "No dismissed alerts." : "Run the price_monitor pipeline to check for market price changes."}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[12px] text-muted-foreground">{data.count} alert{data.count !== 1 ? "s" : ""}</p>
        <button
          onClick={() => setShowDismissed(!showDismissed)}
          className="text-[12px] text-primary hover:underline"
        >
          {showDismissed ? "Show active" : "Show dismissed"}
        </button>
      </div>
      {data.alerts.map((alert) => (
        <AlertCard
          key={alert.Id}
          alert={alert}
          onDismiss={() => dismissMutation.mutate(alert.Id)}
          dismissing={dismissMutation.isPending}
        />
      ))}
    </div>
  );
}

function AlertCard({ alert, onDismiss, dismissing }: {
  alert: PriceAlert;
  onDismiss: () => void;
  dismissing: boolean;
}) {
  const isDown = alert.Direction === "down";
  const Icon = isDown ? TrendingDown : TrendingUp;
  const changePct = alert.Change_Pct != null ? Math.abs(alert.Change_Pct) : null;

  return (
    <div className={cn(
      "rounded-lg border p-4 space-y-2",
      alert.Severity === "critical" ? "border-red-500/30 bg-red-500/5"
        : alert.Severity === "warning" ? "border-amber-500/30 bg-amber-500/5"
        : "border-border bg-background"
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Icon
            className={cn("size-4 shrink-0", isDown ? "text-emerald-500" : "text-red-400")}
            strokeWidth={2.5}
          />
          <div className="min-w-0">
            <span className="text-[13px] font-medium">{alert.Ingredient_Name}</span>
            {alert.Supplier_Name && (
              <span className="text-[11px] text-muted-foreground ml-1.5">via {alert.Supplier_Name}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {changePct != null && (
            <span className={cn(
              "text-[12px] font-mono font-semibold px-1.5 py-0.5 rounded",
              isDown ? "text-emerald-500 bg-emerald-500/10" : "text-red-400 bg-red-400/10"
            )}>
              {isDown ? "−" : "+"}{changePct.toFixed(1)}%
            </span>
          )}
          {!alert.Dismissed && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0 text-muted-foreground"
              onClick={onDismiss}
              disabled={dismissing}
            >
              <X className="size-3" />
            </Button>
          )}
        </div>
      </div>

      {alert.Previous_Price_USD != null && alert.New_Price_USD != null && (
        <p className="text-[12px] text-muted-foreground font-mono">
          ${alert.Previous_Price_USD.toFixed(2)} → ${alert.New_Price_USD.toFixed(2)}/kg
        </p>
      )}

      {alert.Alert_Narrative && (
        <p className="text-[12px] text-foreground/80 leading-relaxed border-t border-border pt-2 mt-2">
          {alert.Alert_Narrative}
        </p>
      )}

      <p className="text-[10px] text-muted-foreground/60">
        Detected {new Date(alert.Detected_At).toLocaleDateString()}
        {alert.Severity !== "info" && (
          <span className={cn(
            "ml-2 uppercase font-semibold text-[9px] px-1 py-0.5 rounded",
            SEVERITY_STYLES[alert.Severity]
          )}>
            {alert.Severity}
          </span>
        )}
      </p>
    </div>
  );
}
