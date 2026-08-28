import { ReactNode } from "react";

export default function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-primary">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-primary/60">{description}</p>}
      </div>
      {action}
    </div>
  );
}
