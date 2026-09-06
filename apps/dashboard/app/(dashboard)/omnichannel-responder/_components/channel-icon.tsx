import { SendIcon, MessageCircleIcon, CameraIcon, MessageSquareIcon, MailIcon, TestTubeIcon } from "lucide-react";
import type { OmniChannel } from "@/types/api";
import { cn } from "@/lib/utils";

// lucide-react dropped brand/logo icons a while back (no InstagramIcon/
// FacebookIcon export) - same reason components/shared/platform-badge.tsx
// renders those platforms as plain colored text badges rather than icons.
// Generic icons + per-channel color are used here for the same reason.
const CHANNEL_META: Record<OmniChannel, { label: string; icon: typeof SendIcon; className: string }> = {
  telegram: { label: "Telegram", icon: SendIcon, className: "bg-sky-500/15 text-sky-600 dark:text-sky-400" },
  whatsapp: { label: "WhatsApp", icon: MessageCircleIcon, className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  instagram: { label: "Instagram", icon: CameraIcon, className: "bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-400" },
  facebook: { label: "Facebook", icon: MessageSquareIcon, className: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  gmail: { label: "Gmail", icon: MailIcon, className: "bg-red-500/15 text-red-600 dark:text-red-400" },
  mock: { label: "Test", icon: TestTubeIcon, className: "bg-muted text-muted-foreground" },
};

export function ChannelIcon({ channel, className }: { channel: OmniChannel; className?: string }) {
  const meta = CHANNEL_META[channel] ?? CHANNEL_META.mock;
  const Icon = meta.icon;
  return (
    <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full", meta.className, className)}>
      <Icon className="size-3.5" />
    </span>
  );
}

export function channelLabel(channel: OmniChannel): string {
  return (CHANNEL_META[channel] ?? CHANNEL_META.mock).label;
}
