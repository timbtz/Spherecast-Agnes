import { TrendingUp, FlaskConical, ShieldCheck, ShieldAlert, FileText, Workflow, Mic, Package, Bell, Route } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export type TabKey = "agnes" | "opportunities" | "ingredients" | "compliance" | "proposals" | "runs" | "suppliers" | "alerts" | "regulatory" | "routes";

const ITEMS: Array<{ key: TabKey; label: string; icon: LucideIcon; group?: string }> = [
  { key: "agnes", label: "Talk to Agnes", icon: Mic },
  { key: "opportunities", label: "Opportunities", icon: TrendingUp },
  { key: "ingredients", label: "Ingredients", icon: FlaskConical },
  { key: "compliance", label: "Compliance", icon: ShieldCheck },
  { key: "proposals", label: "Proposals", icon: FileText },
  { key: "runs", label: "Pipeline Runs", icon: Workflow },
  { key: "suppliers", label: "Suppliers", icon: Package },
  { key: "alerts", label: "Price Alerts", icon: Bell },
  { key: "regulatory", label: "Regulatory", icon: ShieldAlert },
  { key: "routes", label: "Trade Routes", icon: Route },
];

export function Sidebar({ active, onSelect }: { active: TabKey; onSelect: (k: TabKey) => void }) {
  return (
    <aside className="w-[220px] shrink-0 border-r border-border bg-sidebar flex flex-col">
      <div className="px-3 pt-4 pb-2">
        <p className="text-[10.5px] uppercase tracking-[0.08em] text-muted-foreground/70 font-semibold px-2 mb-1.5">
          Workspace
        </p>
        <nav className="flex flex-col gap-0.5">
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.key === active;
            return (
              <button
                key={item.key}
                onClick={() => onSelect(item.key)}
                className={cn(
                  "group relative flex items-center gap-2.5 px-2.5 py-1.5 text-[13px] rounded-md transition-colors text-left",
                  isActive
                    ? "bg-sidebar-accent text-foreground font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )}
              >
                {isActive && (
                  <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-primary" />
                )}
                <Icon className={cn("size-4 shrink-0", isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} strokeWidth={2} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto p-3 border-t border-border">
        <div className="rounded-lg bg-surface-subtle border border-border p-3">
          <p className="text-[12px] font-medium text-foreground mb-1">Quick start</p>
          <p className="text-[11.5px] text-muted-foreground leading-relaxed">
            Tap the orb and say <span className="font-mono text-foreground/80">"Find consolidation opportunities for Vitamin C"</span>.
          </p>
        </div>
      </div>
    </aside>
  );
}
