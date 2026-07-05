import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type Props = {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
};

export function EmptyState({ title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong px-6 py-12 text-center",
        className
      )}
    >
      <h3 className="text-sm font-medium text-ink-primary">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-[13px] leading-5 text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
