import { History, LayoutList, Radar, Upload } from "lucide-react";
import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/today", label: "Hoy", icon: Radar },
  { to: "/conversations", label: "Lista", icon: LayoutList },
  { to: "/manual-import", label: "Importar", icon: Upload },
  { to: "/history", label: "Historial", icon: History },
];

export default function MobileNavigation() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-primary/10 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
      aria-label="Navegación principal"
    >
      {ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
              isActive ? "text-primary" : "text-primary/50"
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={20} strokeWidth={isActive ? 2.4 : 2} aria-hidden="true" />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
