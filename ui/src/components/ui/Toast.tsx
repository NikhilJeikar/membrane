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

type ToastItem = {
  id: number;
  kind: ToastKind;
  title: string;
  subtitle?: string;
};

type ToastContextValue = {
  toast: (kind: ToastKind, title: string, subtitle?: string) => void;
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
    (kind: ToastKind, title: string, subtitle?: string) => {
      const id = nextId.current++;
      setItems((prev) => [...prev, { id, kind, title, subtitle }]);
      setTimeout(() => dismiss(id), 5000);
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
              "pointer-events-auto flex items-start gap-3 rounded-lg border bg-surface-elevated px-4 py-3 shadow-overlay animate-fadeIn",
              kindStyles[item.kind].border
            )}
          >
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
