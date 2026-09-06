import { cn } from "@/lib/utils";

export type MediaTypeFilterValue = "all" | "image" | "video";

const OPTIONS: { value: MediaTypeFilterValue; label: string }[] = [
  { value: "all", label: "Tutti" },
  { value: "image", label: "Immagini" },
  { value: "video", label: "Video" },
];

interface MediaTypeFilterProps {
  value: MediaTypeFilterValue;
  onChange: (value: MediaTypeFilterValue) => void;
  className?: string;
}

export function MediaTypeFilter({ value, onChange, className }: MediaTypeFilterProps) {
  return (
    <div className={cn("inline-flex rounded-md border p-0.5", className)}>
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors",
            value === option.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function filterMediaByType<T extends { mime_type: string }>(media: T[], filter: MediaTypeFilterValue): T[] {
  if (filter === "all") return media;
  return media.filter((m) => m.mime_type.startsWith(`${filter}/`));
}
