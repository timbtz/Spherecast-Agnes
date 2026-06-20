import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 text-[13px] text-muted-foreground", className)}>
      <Loader2 className="size-3.5 animate-spin" />
      <span>{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  icon,
  action,
}: {
  title: string;
  body: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-14 rounded-xl border border-dashed border-border bg-surface-subtle/40">
      {icon && <div className="size-10 rounded-full bg-background border border-border flex items-center justify-center mb-3 text-muted-foreground">{icon}</div>}
      <p className="text-[14px] font-medium text-foreground mb-1">{title}</p>
      <p className="text-[12.5px] text-muted-foreground max-w-sm leading-relaxed">{body}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-status-failed/30 bg-status-failed/5 px-3.5 py-2.5">
      <p className="text-[12.5px] text-status-failed">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-[12px] font-medium text-status-failed hover:underline"
        >
          Retry
        </button>
      )}
    </div>
  );
}
