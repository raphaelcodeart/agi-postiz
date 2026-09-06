"use client";

import type { ReactNode } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}</div>;
}

export const FILTER_ALL_VALUE = "__all__";

interface FilterSelectOption {
  value: string;
  label: string;
}

interface FilterSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: FilterSelectOption[];
  placeholder: string;
  allLabel?: string;
}

export function FilterSelect({ value, onChange, options, placeholder, allLabel = "Tutti" }: FilterSelectProps) {
  // Base UI's <Select.Value> shows the raw value in the trigger unless the
  // Root is given an items map - without it, it doesn't know "__all__" means
  // "Tutti" or that a status slug like "draft" means "Bozza".
  const items = [{ value: FILTER_ALL_VALUE, label: allLabel }, ...options];

  return (
    <Select
      items={items}
      value={value || FILTER_ALL_VALUE}
      onValueChange={(next) => onChange(!next || next === FILTER_ALL_VALUE ? "" : next)}
    >
      <SelectTrigger className="min-w-40">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={FILTER_ALL_VALUE}>{allLabel}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
