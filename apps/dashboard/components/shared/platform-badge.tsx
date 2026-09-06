import { GlobeIcon } from "lucide-react";
import { FaInstagram, FaFacebook, FaLinkedin, FaTiktok, FaYoutube, FaXTwitter, FaThreads } from "react-icons/fa6";
import type { IconType } from "react-icons";
import { cn } from "@/lib/utils";

// Keyed by "twitter" - Buffer's own API reports X/Twitter channels with
// service/platform="twitter", never "x" (confirmed against production data,
// see campaign_resolver.py PLATFORM_TEXT_LIMITS for the same finding on the
// backend). Using "x" here made every real X/Twitter channel fall back to the
// generic muted style below instead of showing as a proper "X" badge.
const PLATFORM_STYLES: Record<string, string> = {
  instagram: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400",
  facebook: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  linkedin: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
  tiktok: "bg-zinc-500/10 text-zinc-700 dark:text-zinc-300",
  youtube: "bg-red-500/10 text-red-600 dark:text-red-400",
  twitter: "bg-zinc-500/10 text-zinc-900 dark:text-zinc-100",
  threads: "bg-zinc-500/10 text-zinc-900 dark:text-zinc-100",
};

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  youtube: "YouTube",
  twitter: "X",
  threads: "Threads",
};

// Reused wherever a platform needs a human label without the full badge
// (e.g. the Bacheca channel-picker options: "{channel name} - {platform}").
export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform.toLowerCase().trim()] ?? platform;
}

// react-icons/fa6 (Font Awesome 6) - the real official logo marks, unlike
// lucide-react (see PLATFORM_STYLES comment above - no brand icons there).
// Single-color glyphs (fill="currentColor"), so the actual brand color comes
// from PLATFORM_ICON_COLORS below, not from the SVG itself.
const PLATFORM_ICONS: Record<string, IconType> = {
  instagram: FaInstagram,
  facebook: FaFacebook,
  linkedin: FaLinkedin,
  tiktok: FaTiktok,
  youtube: FaYoutube,
  twitter: FaXTwitter,
  threads: FaThreads,
};

// Real brand colors, rendered on a fixed white circle (see PlatformIcon
// below) regardless of the app's own light/dark theme - same convention
// every "connected app" list uses (Buffer's own UI included), since a few of
// these marks (TikTok/X/Threads) are black and would vanish on a dark
// background. No dark: variant needed here for exactly that reason.
// Instagram has no single official color (its mark is a gradient) - fuchsia
// is the closest single-color approximation, same choice PLATFORM_STYLES
// already made for the pill badge.
const PLATFORM_ICON_COLORS: Record<string, string> = {
  instagram: "text-fuchsia-600",
  facebook: "text-[#1877F2]",
  linkedin: "text-[#0A66C2]",
  tiktok: "text-zinc-900",
  youtube: "text-[#FF0000]",
  twitter: "text-zinc-900",
  threads: "text-zinc-900",
};

interface PlatformBadgeProps {
  platform: string;
  className?: string;
}

// Small circular icon badge with the official platform logo - used as its
// own "which platform" column (e.g. the "Canali social" list), separate
// from PlatformBadge's text+color pill below.
export function PlatformIcon({ platform, className }: PlatformBadgeProps) {
  const key = platform.toLowerCase().trim();
  const color = PLATFORM_ICON_COLORS[key] ?? "text-muted-foreground";
  const Icon = PLATFORM_ICONS[key] ?? GlobeIcon;

  return (
    <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full bg-white ring-1 ring-border", color, className)}>
      <Icon className="size-4" />
    </span>
  );
}

export function PlatformBadge({ platform, className }: PlatformBadgeProps) {
  const key = platform.toLowerCase().trim();
  const style = PLATFORM_STYLES[key] ?? "bg-muted text-muted-foreground";
  const label = PLATFORM_LABELS[key] ?? platform;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium",
        style,
        className
      )}
    >
      <span className="size-1.5 shrink-0 rounded-full bg-current" />
      {label}
    </span>
  );
}
