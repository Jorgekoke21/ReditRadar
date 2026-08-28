export default function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-card border border-primary/10 bg-white px-6 py-12 text-sm text-primary/60">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary/20 border-t-primary" aria-hidden="true" />
      {label}
    </div>
  );
}
