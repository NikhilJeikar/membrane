import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "../../lib/utils";

type Props = {
  code: string;
  className?: string;
};

export function CodeBlock({ code, className }: Props) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div
      className={cn(
        "group relative rounded-md border border-line bg-black/30",
        className
      )}
    >
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words p-3 pr-12 font-mono text-[13px] leading-6 text-ink-primary">
        {code}
      </pre>
      <button
        type="button"
        aria-label="Copy to clipboard"
        onClick={copy}
        className="absolute right-2 top-2 rounded-md border border-line bg-surface-elevated p-1.5 text-ink-muted transition hover:text-ink-primary"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
