import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, ChevronDown, ChevronUp } from "lucide-react";
import { agnesApi } from "@/lib/agnesApi";
import type { RegulatoryAlert } from "@/types/agnes";
import { LoadingState, EmptyState, ErrorState } from "@/components/shared/States";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES = {
  HIGH: "bg-red-500/10 border-red-500/30 text-red-500",
  MEDIUM: "bg-amber-500/10 border-amber-500/30 text-amber-500",
  LOW: "bg-blue-500/10 border-blue-500/30 text-blue-500",
};

function getSeverity(alert: RegulatoryAlert): "HIGH" | "MEDIUM" | "LOW" {
  if (alert.status === "D") return "HIGH";
  const snapshots = alert.snapshots;
  if (snapshots.length >= 2) {
    const latest = snapshots[snapshots.length - 1].max_daily_exposure;
    const prior = snapshots[0].max_daily_exposure;
    if (latest != null && prior != null && prior > 0) {
      const drop = (prior - latest) / prior;
      if (drop > 0.3) return "HIGH";
      if (drop > 0.1) return "MEDIUM";
    }
  }
  return "LOW";
}

export function RegulatoryAlertsView() {
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["regulatory-alerts"],
    queryFn: () => agnesApi.regulatoryAlerts(),
  });

  const runPipeline = useMutation({
    mutationFn: () => agnesApi.runPipeline("regulatory_drift_alert" as any),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["regulatory-alerts"] }), 5000);
    },
  });

  if (isLoading) return <LoadingState label="Loading regulatory alerts…" />;
  if (error) return <ErrorState message="Failed to load regulatory alerts." />;

  if (!data?.alerts?.length) {
    return (
      <EmptyState
        icon={<ShieldAlert className="size-4" />}
        title="No regulatory alerts"
        body="Run the regulatory_drift_alert pipeline to scan for FDA IID changes."
        action={
          <Button size="sm" onClick={() => runPipeline.mutate()} disabled={runPipeline.isPending}>
            {runPipeline.isPending ? "Running…" : "Run Pipeline"}
          </Button>
        }
      />
    );
  }

  const filtered = severityFilter === "ALL"
    ? data.alerts
    : data.alerts.filter(a => getSeverity(a) === severityFilter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-muted-foreground">{data.count} alert{data.count !== 1 ? "s" : ""}</p>
        <div className="flex items-center gap-2">
          {["ALL", "HIGH", "MEDIUM", "LOW"].map(s => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={cn(
                "text-[11px] px-2 py-0.5 rounded font-medium border transition-colors",
                severityFilter === s
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:border-foreground/30"
              )}
            >{s}</button>
          ))}
          <Button size="sm" variant="outline" onClick={() => runPipeline.mutate()} disabled={runPipeline.isPending}>
            {runPipeline.isPending ? "Running…" : "Refresh"}
          </Button>
        </div>
      </div>

      {filtered.map(alert => (
        <RegulatoryAlertCard
          key={`${alert.change_id}-${alert.route}`}
          alert={alert}
          severity={getSeverity(alert)}
        />
      ))}
    </div>
  );
}

function RegulatoryAlertCard({ alert, severity }: { alert: RegulatoryAlert; severity: "HIGH" | "MEDIUM" | "LOW" }) {
  const [expanded, setExpanded] = useState(false);
  const statusLabel = alert.status === "C" ? "Corrected" : alert.status === "D" ? "Deleted" : "Revised";
  const snapshots = alert.snapshots;

  return (
    <div className={cn("rounded-lg border p-4 space-y-2", SEVERITY_STYLES[severity])}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-semibold">{alert.ingredient_name}</span>
            <span className={cn("text-[10px] uppercase px-1.5 py-0.5 rounded font-semibold border", SEVERITY_STYLES[severity])}>
              {severity}
            </span>
            <span className="text-[10px] uppercase px-1.5 py-0.5 rounded border border-border text-muted-foreground">
              {statusLabel}
            </span>
          </div>
          {alert.route && (
            <p className="text-[11px] text-muted-foreground mt-0.5 font-mono">
              {alert.route} · {alert.dosage_form}
            </p>
          )}
        </div>
        <button onClick={() => setExpanded(e => !e)} className="text-muted-foreground hover:text-foreground shrink-0">
          {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </button>
      </div>

      {snapshots.length >= 2 && (
        <div className="flex items-center gap-3 text-[12px] font-mono">
          <span className="text-muted-foreground">{snapshots[0].snapshot_date}:</span>
          <span>{snapshots[0].max_daily_exposure ?? "–"} {snapshots[0].mde_uom}</span>
          <span className="text-muted-foreground">→</span>
          <span className="text-muted-foreground">{snapshots[snapshots.length - 1].snapshot_date}:</span>
          <span>{snapshots[snapshots.length - 1].max_daily_exposure ?? "–"} {snapshots[snapshots.length - 1].mde_uom}</span>
        </div>
      )}

      {expanded && alert.regulatory_drift_reason && (
        <p className="text-[12px] text-foreground/80 leading-relaxed border-t border-inherit pt-2 mt-2">
          {alert.regulatory_drift_reason}
        </p>
      )}
    </div>
  );
}
