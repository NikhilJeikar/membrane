import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "../../lib/utils";

export type ToastKind = "success" | "error" | "info";

export type ToastAction = {
  label: string;
  variant?: "primary" | "secondary";
  onClick: () => void | Promise<void>;
};

type ToastItem = {
  id: number;
  kind: ToastKind;
  title: string;
  subtitle?: string;
  actions?: ToastAction[];
};

type ToastContextValue = {
  toast: (
    kind: ToastKind,
    title: string,
    subtitle?: string,
    actions?: ToastAction[]
  ) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const kindStyles: Record<ToastKind, { border: string; icon: ReactNode }> = {
  success: {
    border: "border-emerald-500/40",
    icon: <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />,
  },
  error: {
    border: "border-red-500/40",
    icon: <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />,
  },
  info: {
    border: "border-sky-500/40",
    icon: <Info className="h-4 w-4 shrink-0 text-sky-400" />,
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (kind: ToastKind, title: string, subtitle?: string, actions?: ToastAction[]) => {
      const id = nextId.current++;
      setItems((prev) => [...prev, { id, kind, title, subtitle, actions }]);
      const duration = actions?.length ? 12000 : 5000;
      setTimeout(() => dismiss(id), duration);
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto rounded-lg border bg-surface-elevated shadow-overlay animate-fadeIn",
              kindStyles[item.kind].border
            )}
          >
            <div className="flex items-start gap-3 px-4 py-3">
              {kindStyles[item.kind].icon}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink-primary">{item.title}</p>
                {item.subtitle && (
                  <p className="mt-0.5 break-words text-xs leading-5 text-ink-secondary">
                    {item.subtitle}
                  </p>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => dismiss(item.id)}
                className="rounded p-0.5 text-ink-muted transition hover:text-ink-primary"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            {item.actions && item.actions.length > 0 && (
              <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/10 px-3 py-2">
                {item.actions.map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => {
                      void Promise.resolve(action.onClick());
                      dismiss(item.id);
                    }}
                    className={cn(
                      "rounded px-2.5 py-1 text-xs font-medium transition",
                      action.variant === "primary"
                        ? "bg-accent text-white hover:bg-accent-hover"
                        : "text-ink-secondary hover:bg-white/10 hover:text-ink-primary"
                    )}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx.toast;
}
