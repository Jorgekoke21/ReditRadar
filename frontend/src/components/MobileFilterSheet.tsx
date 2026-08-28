import { X } from "lucide-react";
import { ReactNode, useEffect } from "react";

export default function MobileFilterSheet({
  open,
  onClose,
  title = "Filtros",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end md:hidden" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-primary/30" onClick={onClose} />
      <div className="relative max-h-[80vh] w-full overflow-y-auto rounded-t-2xl bg-white p-4 pb-[calc(env(safe-area-inset-bottom)+16px)] shadow-subtle">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-primary">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Cerrar filtros"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-primary/60 hover:bg-primary/5"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
