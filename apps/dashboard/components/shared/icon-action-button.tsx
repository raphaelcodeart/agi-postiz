import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface IconActionButtonProps {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  destructive?: boolean;
  spinning?: boolean;
  title?: string;
  className?: string;
}

// Icon-only row actions (Duplica/Rigenera/Archivia/Elimina...) read as unlabeled
// glyphs at a glance - this stacks a small caption under the icon instead, kept
// compact enough to still fit in a dense table row.
export function IconActionButton({ icon: Icon, label, onClick, disabled, destructive, spinning, title, className }: IconActionButtonProps) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      className={cn("h-auto flex-col gap-0.5 px-2 py-1", destructive && "text-destructive hover:text-destructive", className)}
    >
      <Icon className={cn("size-3.5", spinning && "animate-spin")} />
      <span className="text-[10px] leading-none whitespace-nowrap">{label}</span>
    </Button>
  );
}
