import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export type TagTone = "green" | "red" | "amber" | "blue" | "purple" | "gray";

const toneClasses: Record<TagTone, string> = {
  green: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
  red: "bg-red-500/10 text-red-300 border-red-500/20",
  amber: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  blue: "bg-sky-500/10 text-sky-300 border-sky-500/20",
  purple: "bg-purple-500/10 text-purple-300 border-purple-500/20",
  gray: "bg-white/5 text-ink-secondary border-white/10",
};

type Props = HTMLAttributes<HTMLSpanElement> & { tone?: TagTone };

export function Tag({ tone = "gray", className, ...props }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}
