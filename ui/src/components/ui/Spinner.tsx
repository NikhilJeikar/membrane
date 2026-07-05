import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

type Props = {
  label?: string;
  className?: string;
};

export function Spinner({ label, className }: Props) {
  return (
    <div className={cn("flex items-center gap-2.5 py-8 text-ink-secondary", className)}>
      <Loader2 className="h-4 w-4 animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}
