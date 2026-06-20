import type { Grade } from "@/types/agnes";
import { cn } from "@/lib/utils";

const STYLES: Record<Grade, string> = {
  supplement: "bg-primary/10 text-primary border-primary/20",
  food: "bg-status-completed/10 text-status-completed border-status-completed/20",
  excipient: "bg-muted text-muted-foreground border-border",
  sweetener: "bg-status-skipped/10 text-status-skipped border-status-skipped/30",
  flavor: "bg-orb-thinking/10 text-orb-thinking border-orb-thinking/20",
};

export function GradePill({ grade, className }: { grade?: Grade | null; className?: string }) {
  if (!grade) return null;
  return (
    <span className={cn("pill border capitalize", STYLES[grade], className)}>
      {grade}
    </span>
  );
}
