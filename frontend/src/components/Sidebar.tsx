import {
  Bell,
  History,
  LayoutList,
  LogOut,
  Radar,
  Settings as SettingsIcon,
  Tags,
  Upload,
  Users,
  Wrench,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";

const MAIN_ITEMS = [
  { to: "/today", label: "Hoy", icon: Radar },
  { to: "/conversations", label: "Conversaciones", icon: LayoutList },
  { to: "/manual-import", label: "Importar", icon: Upload },
  { to: "/communities", label: "Comunidades", icon: Users },
  { to: "/topics", label: "Temas", icon: Tags },
  { to: "/history", label: "Historial", icon: History },
];

const SECONDARY_ITEMS = [
  { to: "/alerts", label: "Alertas", icon: Bell },
  { to: "/settings", label: "Configuración", icon: SettingsIcon },
  { to: "/diagnostics", label: "Diagnóstico", icon: Wrench },
];

function NavItem({ to, label, icon: Icon }: { to: string; label: string; icon: typeof Radar }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          isActive ? "bg-primary text-accent" : "text-primary/80 hover:bg-primary/5 hover:text-primary"
        }`
      }
    >
      <Icon size={18} strokeWidth={2} aria-hidden="true" />
      {label}
    </NavLink>
  );
}

export default function Sidebar() {
  const { profile, logout } = useAuth();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-primary/10 bg-white px-3 py-4 md:flex">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-accent">
          <Radar size={18} aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight text-primary">Radar de Conversaciones</p>
          <p className="text-[11px] leading-tight text-primary/50">Radarin</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1" aria-label="Navegación principal">
        {MAIN_ITEMS.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
        <div className="my-3 border-t border-primary/10" />
        {SECONDARY_ITEMS.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
      </nav>

      <div className="mt-4 border-t border-primary/10 pt-3">
        <p className="truncate px-2 text-xs text-primary/50">{profile?.email}</p>
        <button
          onClick={logout}
          className="mt-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-primary/70 hover:bg-primary/5 hover:text-primary"
        >
          <LogOut size={16} aria-hidden="true" />
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
