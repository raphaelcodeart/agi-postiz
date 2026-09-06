import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  hint?: string;
  tone?: "default" | "success" | "warning" | "destructive";
  loading?: boolean;
}

const toneClasses: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
};

const toneIconClasses: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  destructive: "bg-destructive/10 text-destructive",
};

const toneAccentClasses: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "bg-brand-gradient",
  success: "bg-success",
  warning: "bg-warning",
  destructive: "bg-destructive",
};

export function StatCard({ label, value, icon: Icon, hint, tone = "default", loading }: StatCardProps) {
  return (
    <Card className="relative animate-in fade-in slide-in-from-bottom-1 duration-500">
      <div className={cn("absolute inset-x-0 top-0 h-0.5 opacity-70", toneAccentClasses[tone])} />
      <CardContent className="flex items-start justify-between gap-3 px-4 py-4">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <div className="h-7 w-16 animate-pulse rounded bg-muted" />
          ) : (
            <p className={cn("text-2xl font-semibold tabular-nums", toneClasses[tone])}>{value}</p>
          )}
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
        {Icon && (
          <div className={cn("rounded-lg p-2 transition-transform duration-300 group-hover/card:scale-110", toneIconClasses[tone])}>
            <Icon className="size-4" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
