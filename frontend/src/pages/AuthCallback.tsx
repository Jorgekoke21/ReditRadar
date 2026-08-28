import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";

/**
 * Supabase redirects the magic-link click here. supabase-js's
 * `detectSessionInUrl: true` parses the URL fragment/query on its own as
 * soon as the client is constructed (which AuthProvider's bootstrap effect
 * already does) and fires `onAuthStateChange`, which is what actually
 * populates `profile`. This page just waits for that and shows the right
 * state — including a real "token inválido" error read from the URL when
 * Supabase itself reports one (e.g. an expired or already-used link).
 */
export default function AuthCallback() {
  const { profile, loading } = useAuth();
  const [urlError, setUrlError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, "") || window.location.search);
    const description = params.get("error_description") || params.get("error");
    if (description) setUrlError(decodeURIComponent(description.replace(/\+/g, " ")));
  }, []);

  if (urlError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <div className="w-full max-w-sm">
          <ErrorState message={`Enlace inválido o expirado: ${urlError}`} />
          <a href="/login" className="mt-4 block text-center text-sm font-medium text-primary underline">
            Volver a intentarlo
          </a>
        </div>
      </div>
    );
  }

  if (!loading && profile) return <Navigate to="/today" replace />;

  if (!loading && !profile) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <div className="w-full max-w-sm">
          <ErrorState message="No se pudo iniciar sesión con este enlace." />
          <a href="/login" className="mt-4 block text-center text-sm font-medium text-primary underline">
            Volver a intentarlo
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <LoadingState label="Iniciando sesión…" />
    </div>
  );
}
