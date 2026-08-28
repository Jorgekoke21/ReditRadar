import { ChevronDown } from "lucide-react";
import { ReactNode, useState } from "react";

export default function SectionDisclosure({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-primary/10 first:border-t-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between py-3 text-left text-sm font-medium text-primary"
        aria-expanded={open}
      >
        {title}
        <ChevronDown
          size={16}
          className={`text-primary/50 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  );
}
