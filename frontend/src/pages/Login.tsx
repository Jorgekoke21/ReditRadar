import { Mail, Radar, ShieldAlert } from "lucide-react";
import { FormEvent, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../lib/auth";
import LoadingState from "../components/LoadingState";

export default function Login() {
  const { profile, loading, config, configError, sendMagicLink, magicLinkStatus, magicLinkError, loginWithDevEmail } =
    useAuth();
  const [email, setEmail] = useState("");
  const [devStatus, setDevStatus] = useState<"idle" | "sending" | "error">("idle");
  const [devError, setDevError] = useState("");
  const [searchParams] = useSearchParams();
  const expired = searchParams.get("reason") === "expired";

  if (!loading && profile) return <Navigate to="/today" replace />;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <LoadingState label="Cargando…" />
      </div>
    );
  }

  if (configError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <div className="w-full max-w-sm rounded-card border border-red-200 bg-white p-7 text-center shadow-subtle">
          <ShieldAlert className="mx-auto mb-3 text-red-500" size={28} aria-hidden="true" />
          <h1 className="text-lg font-semibold text-primary">Error de configuración</h1>
          <p className="mt-2 text-sm text-primary/60">
            Este entorno está configurado para usar Supabase Auth (<code>AUTH_MODE=supabase</code>) pero el
            frontend no tiene <code>VITE_SUPABASE_URL</code> / <code>VITE_SUPABASE_ANON_KEY</code> configurados, o
            el backend no expone una configuración válida. No es posible iniciar sesión hasta corregir esto — ver{" "}
            <code>docs/authentication.md</code>.
          </p>
        </div>
      </div>
    );
  }

  async function handleMagicLink(e: FormEvent) {
    e.preventDefault();
    await sendMagicLink(email);
  }

  async function handleDevLogin(e: FormEvent) {
    e.preventDefault();
    setDevStatus("sending");
    setDevError("");
    try {
      await loginWithDevEmail(email);
    } catch (err) {
      setDevStatus("error");
      setDevError(err instanceof Error ? err.message : "No se pudo iniciar sesión");
    }
  }

  const isDevMode = config?.auth_mode === "development";
  const supabaseAvailable = !!(config?.supabase_url && config?.supabase_anon_key);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm rounded-card border border-primary/10 bg-white p-7 shadow-subtle">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-accent">
            <Radar size={22} aria-hidden="true" />
          </div>
          <h1 className="text-lg font-semibold text-primary">Radar de Conversaciones</h1>
          <p className="mt-1 text-sm text-primary/60">Accede con un enlace mágico a tu correo</p>
        </div>

        {expired && (
          <p role="status" className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Tu sesión ha expirado. Vuelve a iniciar sesión.
          </p>
        )}

        {isDevMode && (
          <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-center text-xs font-medium text-amber-800">
            Modo autenticación de desarrollo
          </p>
        )}

        {supabaseAvailable && (
          <form onSubmit={handleMagicLink} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-primary/60">
              Correo electrónico
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@email.com"
                className="min-h-[44px] rounded-lg border border-primary/15 px-3 text-sm text-primary placeholder:text-primary/35 focus:border-primary"
              />
            </label>

            <button
              type="submit"
              disabled={magicLinkStatus === "sending"}
              className="flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-primary text-sm font-semibold text-accent hover:bg-primary-hover disabled:opacity-60"
            >
              <Mail size={16} aria-hidden="true" />
              {magicLinkStatus === "sending" ? "Enviando enlace…" : "Enviar enlace mágico"}
            </button>

            {magicLinkStatus === "sent" && (
              <p role="status" className="text-center text-sm text-primary">
                Enlace enviado. Revisa tu correo y haz clic para entrar.
              </p>
            )}
            {magicLinkStatus === "error" && <p className="text-center text-sm text-red-600">{magicLinkError}</p>}
          </form>
        )}

        {isDevMode && (
          <details className={supabaseAvailable ? "mt-5 border-t border-primary/10 pt-4" : ""} open={!supabaseAvailable}>
            {supabaseAvailable && (
              <summary className="cursor-pointer text-xs font-medium text-primary/50">
                Usar acceso de desarrollo en su lugar
              </summary>
            )}
            <form onSubmit={handleDevLogin} className="mt-3 flex flex-col gap-3">
              {!supabaseAvailable && (
                <label className="flex flex-col gap-1 text-xs font-medium text-primary/60">
                  Correo electrónico (modo desarrollo)
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="tu@email.com"
                    className="min-h-[44px] rounded-lg border border-primary/15 px-3 text-sm text-primary placeholder:text-primary/35 focus:border-primary"
                  />
                </label>
              )}
              <button
                type="submit"
                disabled={devStatus === "sending"}
                className="min-h-[44px] rounded-lg border border-primary/20 text-sm font-semibold text-primary hover:bg-primary/5 disabled:opacity-60"
              >
                {devStatus === "sending" ? "Entrando…" : "Continuar en modo desarrollo"}
              </button>
              {devStatus === "error" && <p className="text-center text-sm text-red-600">{devError}</p>}
            </form>
          </details>
        )}

        <p className="mt-5 text-center text-xs leading-relaxed text-primary/45">
          {isDevMode
            ? "Este entorno acepta también un acceso de desarrollo sin verificación, solo para uso local — nunca disponible cuando AUTH_MODE=supabase."
            : "Acceso mediante Supabase Auth real. Introduce tu correo y recibirás un enlace de un solo uso."}
        </p>
      </div>
    </div>
  );
}
