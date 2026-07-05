import * as SwitchPrimitive from "@radix-ui/react-switch";
import { useId } from "react";
import { cn } from "../../lib/utils";

type Props = {
  label?: string;
  helper?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
};

export function Switch({ label, helper, checked, onCheckedChange, disabled, className }: Props) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-3">
        <SwitchPrimitive.Root
          id={id}
          checked={checked}
          onCheckedChange={onCheckedChange}
          disabled={disabled}
          className={cn(
            "relative h-5 w-9 shrink-0 rounded-full border border-transparent transition-colors outline-none",
            "focus-visible:ring-2 focus-visible:ring-white/30 disabled:opacity-40",
            checked ? "bg-accent" : "bg-white/15"
          )}
        >
          <SwitchPrimitive.Thumb
            className={cn(
              "block h-4 w-4 translate-x-0.5 rounded-full bg-white transition-transform",
              "data-[state=checked]:translate-x-[18px]"
            )}
          />
        </SwitchPrimitive.Root>
        {label && (
          <label htmlFor={id} className="cursor-pointer text-sm text-ink-primary">
            {label}
          </label>
        )}
      </div>
      {helper && <p className="ml-12 text-[13px] leading-5 text-ink-muted">{helper}</p>}
    </div>
  );
}
