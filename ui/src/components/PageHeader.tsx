type Props = {
  title: string;
  description?: string;
};

export default function PageHeader({ title, description }: Props) {
  return (
    <header className="mb-8 border-b border-line pb-5">
      <h1 className="text-xl font-semibold tracking-tight text-ink-primary">{title}</h1>
      {description && (
        <p className="mt-1.5 max-w-2xl text-[13px] leading-5 text-ink-muted">{description}</p>
      )}
    </header>
  );
}
