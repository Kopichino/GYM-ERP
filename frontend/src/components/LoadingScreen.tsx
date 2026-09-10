export default function LoadingScreen({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-[var(--color-bg)] text-[var(--color-text-muted)]">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent)]" />
      <p className="text-sm">{label}</p>
    </div>
  );
}
