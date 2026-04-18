import { cn } from "@/lib/utils";

interface ScoreBarProps {
  score: number; // 0..1
  className?: string;
  showValue?: boolean;
}

// Color-coded consolidation score bar.
export function ScoreBar({ score, className, showValue = true }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color =
    score >= 0.75 ? "hsl(var(--status-completed))"
    : score >= 0.5 ? "hsl(var(--status-skipped))"
    : "hsl(var(--status-failed))";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden min-w-[60px]">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      {showValue && (
        <span className="text-[12px] font-mono tabular-nums text-foreground/80 min-w-[36px] text-right">
          {(score * 100).toFixed(0)}
        </span>
      )}
    </div>
  );
}
