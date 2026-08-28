export interface ToastItem {
  id: number;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export default function ConfirmationToast({ toast }: { toast: ToastItem }) {
  return (
    <div
      role="status"
      className="pointer-events-auto flex items-center gap-3 rounded-lg bg-primary px-4 py-2.5 text-sm text-white shadow-subtle"
    >
      <span>{toast.message}</span>
      {toast.actionLabel && toast.onAction && (
        <button onClick={toast.onAction} className="font-semibold text-accent hover:underline">
          {toast.actionLabel}
        </button>
      )}
    </div>
  );
}
