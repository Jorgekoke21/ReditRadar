import { ReactNode } from "react";
import { Inbox } from "lucide-react";

export default function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: typeof Inbox;
}) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-primary/15 bg-white px-6 py-12 text-center">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-surface text-primary/50">
        <Icon size={20} aria-hidden="true" />
      </div>
      <p className="text-sm font-medium text-primary">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-primary/60">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
