import { forwardRef, useId, type InputHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  helper?: string;
  inputClassName?: string;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { label, helper, className, inputClassName, id, ...props },
  ref
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label htmlFor={inputId} className="text-[13px] font-medium text-ink-secondary">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={cn(
          "h-9 w-full rounded-md border border-line bg-surface-input px-3 text-sm text-ink-primary outline-none transition",
          "placeholder:text-ink-muted focus:border-line-strong disabled:opacity-50",
          inputClassName
        )}
        {...props}
      />
      {helper && <p className="text-xs text-ink-muted">{helper}</p>}
    </div>
  );
});
