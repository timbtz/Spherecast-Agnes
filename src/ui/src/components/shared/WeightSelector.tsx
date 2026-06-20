import { cn } from "@/lib/utils";

interface WeightSelectorProps {
  label: string;
  description: string;
  value: number;
  onChange: (v: number) => void;
  icon?: React.ReactNode;
}

export function WeightSelector({ label, description, value, onChange, icon }: WeightSelectorProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        {icon && <span className="text-muted-foreground">{icon}</span>}
        <span className="text-[13px] font-medium">{label}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">{description}</p>
      <div className="flex gap-1.5 mt-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={cn(
              "h-7 w-9 rounded text-[11px] font-mono border transition-colors",
              n <= value
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted text-muted-foreground border-border hover:bg-accent"
            )}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}
