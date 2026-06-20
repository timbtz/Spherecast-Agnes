import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useApiHealth } from "@/hooks/useApiHealth";
import { agnesApi } from "@/lib/agnesApi";
import { SpherecastWordmark } from "@/components/brand/SpherecastMark";
import { cn } from "@/lib/utils";

export function TopBar() {
  const { apiOnline, mode, toggleMode } = useApiHealth();
  const { data: alertData } = useQuery({
    queryKey: ["alert-count"],
    queryFn: () => agnesApi.alertCount(),
    refetchInterval: 60_000,
    enabled: apiOnline,
  });
  const alertCount = alertData?.count ?? 0;

  return (
    <header className="h-12 shrink-0 border-b border-border flex items-center justify-between px-5 bg-background/80 backdrop-blur-sm relative z-20">
      <div className="flex items-center gap-2.5">
        <SpherecastWordmark height={20} className="text-foreground" />
        <span className="text-muted-foreground text-[13px] mx-1">/</span>
        <span className="text-muted-foreground text-[13px] font-medium">Agnes</span>
      </div>

      <div className="flex items-center gap-3">
        {alertCount > 0 && (
          <div className="relative">
            <Bell className="size-4 text-muted-foreground animate-status-pulse" strokeWidth={2} />
            <span className="absolute -top-1.5 -right-1.5 size-4 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center leading-none">
              {alertCount > 9 ? "9+" : alertCount}
            </span>
          </div>
        )}

        <button
          onClick={toggleMode}
          className={cn(
            "pill border transition-colors",
            mode === "live"
              ? "bg-status-completed/10 text-status-completed border-status-completed/20 hover:bg-status-completed/15"
              : "bg-status-skipped/10 text-status-skipped border-status-skipped/30 hover:bg-status-skipped/20",
          )}
          title="Toggle live ↔ demo data"
        >
          {mode === "live" ? "Live data" : "Demo mode"}
        </button>

        <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <span
            className={cn(
              "size-1.5 rounded-full",
              apiOnline ? "bg-status-completed animate-status-pulse" : "bg-status-failed",
            )}
          />
          <span>Agnes API</span>
          <span className="text-muted-foreground/60 font-mono text-[11px] ml-1">
            {new URL(agnesApi.apiUrl).host}
          </span>
        </div>
      </div>
    </header>
  );
}
