import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "../lib/utils";
import { CodeBlock } from "./ui/CodeBlock";

const components: Components = {
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children, ...props }) => {
    const text = String(children ?? "").replace(/\n$/, "");
    const language = /language-(\w+)/.exec(className ?? "")?.[1];
    const isBlock = Boolean(language) || text.includes("\n");
    if (isBlock) {
      return <CodeBlock code={text} className="my-3" />;
    }
    return (
      <code
        className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em] text-ink-primary"
        {...props}
      >
        {children}
      </code>
    );
  },
  p: ({ children }) => <p className="mb-3 leading-7 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5 leading-7 last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5 leading-7 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-7">{children}</li>,
  h1: ({ children }) => (
    <h1 className="mb-3 mt-4 text-xl font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-2 mt-3 text-sm font-semibold first:mt-0">{children}</h4>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-white/20 pl-4 text-ink-secondary last:mb-0">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-line" />,
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/5">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-line px-3 py-2 font-medium text-ink-primary">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border border-line px-3 py-2 text-ink-secondary">{children}</td>
  ),
  strong: ({ children }) => <strong className="font-semibold text-ink-primary">{children}</strong>,
  em: ({ children }) => <em className="italic text-ink-secondary">{children}</em>,
};

type Props = {
  content: string;
  className?: string;
};

export function MarkdownContent({ content, className }: Props) {
  return (
    <div className={cn("min-w-0 text-[0.95rem] text-ink-primary", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
