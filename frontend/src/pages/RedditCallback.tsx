import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import { api } from "../lib/api";

type Phase = "connecting" | "connected" | "cancelled" | "invalid_state" | "error";

const STATE_KEY = "radarin_reddit_oauth_state";

/**
 * Reddit redirects the browser here after the user approves (or denies) the
 * app. This page exists because that redirect carries no Authorization
 * header — the session token lives in this app's storage, not in a cookie —
 * so the backend cannot authenticate the redirect itself. Instead we read
 * `code`/`state` here and hand them to the API over a normal authenticated
 * request, where the account comes from the session rather than the URL.
 */
export default function RedditCallback() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>("connecting");
  const [detail, setDetail] = useState("");
  // React 18 StrictMode double-invokes effects in dev; the OAuth code is
  // single-use, so a second exchange would fail against a consumed state.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const params = new URLSearchParams(window.location.search);
    const error = params.get("error");
    const code = params.get("code");
    const state = params.get("state");
    const expected = sessionStorage.getItem(STATE_KEY);
    sessionStorage.removeItem(STATE_KEY);

    if (error) {
      setPhase("cancelled");
      setDetail(error);
      return;
    }
    if (!code || !state) {
      setPhase("invalid_state");
      setDetail("Faltan los parámetros code o state en la respuesta de Reddit.");
      return;
    }
    // Local pre-check only. The backend re-validates the state against its
    // own account-bound record, which is what actually protects the flow.
    if (expected && expected !== state) {
      setPhase("invalid_state");
      setDetail("El state devuelto no coincide con el que inició la conexión.");
      return;
    }

    api
      .post("/api/reddit/callback", { code, state })
      .then(() => {
        setPhase("connected");
        setTimeout(() => navigate("/settings", { replace: true }), 1200);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : "Error desconocido";
        setPhase(/state/i.test(message) ? "invalid_state" : "error");
        setDetail(message);
      });
  }, [navigate]);

  if (phase === "connecting") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <LoadingState label="Conectando Reddit…" />
      </div>
    );
  }

  if (phase === "connected") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <div className="w-full max-w-sm text-center">
          <p className="text-sm font-medium text-primary">Conectado correctamente.</p>
          <p className="mt-1 text-sm text-primary/60">Volviendo a Configuración…</p>
        </div>
      </div>
    );
  }

  const message =
    phase === "cancelled"
      ? "Conexión cancelada."
      : phase === "invalid_state"
        ? "State inválido."
        : "Error de conexión.";

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm">
        <ErrorState message={detail ? `${message} ${detail}` : message} />
        <Link to="/settings" className="mt-4 block text-center text-sm font-medium text-primary underline">
          Volver a Configuración
        </Link>
      </div>
    </div>
  );
}
