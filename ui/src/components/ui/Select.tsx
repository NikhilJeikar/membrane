import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { useId } from "react";
import { cn } from "../../lib/utils";

export type SelectOption = { value: string; label: string };

type Props = {
  label?: string;
  helper?: string;
  value: string;
  options: SelectOption[];
  onValueChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
};

export function Select({
  label,
  helper,
  value,
  options,
  onValueChange,
  placeholder,
  className,
  disabled,
}: Props) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label htmlFor={id} className="text-[13px] font-medium text-ink-secondary">
          {label}
        </label>
      )}
      <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectPrimitive.Trigger
          id={id}
          className={cn(
            "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-line bg-surface-input px-3 text-sm text-ink-primary outline-none transition",
            "focus:border-line-strong disabled:opacity-50 data-[placeholder]:text-ink-muted"
          )}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <ChevronDown className="h-4 w-4 text-ink-muted" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content
            position="popper"
            sideOffset={4}
            className="z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border border-line-strong bg-surface-elevated shadow-overlay animate-fadeIn"
          >
            <SelectPrimitive.Viewport className="max-h-72 p-1">
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  className={cn(
                    "flex cursor-pointer select-none items-center justify-between gap-2 rounded px-2.5 py-1.5 text-sm text-ink-secondary outline-none",
                    "data-[highlighted]:bg-surface-hover data-[highlighted]:text-ink-primary"
                  )}
                >
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator>
                    <Check className="h-3.5 w-3.5 text-accent" />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
      {helper && <p className="text-xs text-ink-muted">{helper}</p>}
    </div>
  );
}
