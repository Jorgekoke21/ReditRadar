import type { Session } from "@supabase/supabase-js";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setDevToken } from "./api";
import { getSupabaseClient } from "./supabaseClient";
import { setActiveToken } from "./tokenStore";
import type { Profile } from "../types";

export interface AuthConfig {
  auth_mode: "development" | "supabase";
  dev_login_available: boolean;
  supabase_url: string;
  supabase_anon_key: string;
}

export type MagicLinkStatus = "idle" | "sending" | "sent" | "error";

interface AuthContextValue {
  profile: Profile | null;
  loading: boolean;
  config: AuthConfig | null;
  /** True once we know for certain Supabase is the active mode but the
   * frontend has no url/anon key to talk to it with — an actionable
   * "error de configuración" state, not a silent fallback. */
  configError: boolean;
  sendMagicLink: (email: string) => Promise<void>;
  magicLinkStatus: MagicLinkStatus;
  magicLinkError: string;
  loginWithDevEmail: (email: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchProfile(): Promise<Profile | null> {
  try {
    return await api.get<Profile>("/api/auth/me");
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [configError, setConfigError] = useState(false);
  const [magicLinkStatus, setMagicLinkStatus] = useState<MagicLinkStatus>("idle");
  const [magicLinkError, setMagicLinkError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8010";
      let cfg: AuthConfig;
      try {
        const res = await fetch(`${API_URL}/api/auth/config`);
        if (!res.ok) throw new Error("config fetch failed");
        cfg = await res.json();
      } catch {
        if (!cancelled) {
          setConfigError(true);
          setLoading(false);
        }
        return;
      }
      if (cancelled) return;
      setConfig(cfg);

      if (cfg.auth_mode === "supabase" && (!cfg.supabase_url || !cfg.supabase_anon_key)) {
        setConfigError(true);
        setLoading(false);
        return;
      }

      let resolvedProfile: Profile | null = null;

      const supabase = getSupabaseClient(cfg.supabase_url, cfg.supabase_anon_key);
      if (supabase) {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (session) {
          setActiveToken(session.access_token);
          resolvedProfile = await fetchProfile();
          setProfile(resolvedProfile);
        }

        supabase.auth.onAuthStateChange(async (event, newSession: Session | null) => {
          if (event === "SIGNED_OUT") {
            setActiveToken(null);
            setProfile(null);
            return;
          }
          if (newSession) {
            setActiveToken(newSession.access_token);
            setProfile(await fetchProfile());
          }
        });
      }

      // Dev token fallback (persisted in localStorage by loginWithDevEmail,
      // or injected directly by the E2E suite): only trust it if no Supabase
      // session already won above, dev auth is allowed, AND a token is
      // actually present. Skipping the getToken() check here would mean
      // calling /api/auth/me with no token at all on every single
      // unauthenticated page load — a guaranteed 401 that (correctly, for a
      // *mid-session* expiry) triggers api.ts's redirect-to-login, which is
      // wrong for this merely-speculative "does a session happen to exist"
      // check and was previously causing a reload loop on first visit.
      if (!resolvedProfile && cfg.dev_login_available && getToken()) {
        const existing = await fetchProfile();
        if (existing) setProfile(existing);
      }

      if (!cancelled) setLoading(false);
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function sendMagicLink(email: string) {
    if (!config) return;
    const supabase = getSupabaseClient(config.supabase_url, config.supabase_anon_key);
    if (!supabase) {
      setMagicLinkStatus("error");
      setMagicLinkError("Supabase no está configurado en este entorno.");
      return;
    }
    setMagicLinkStatus("sending");
    setMagicLinkError("");
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) {
      setMagicLinkStatus("error");
      setMagicLinkError(error.message);
      return;
    }
    setMagicLinkStatus("sent");
  }

  async function loginWithDevEmail(email: string) {
    const session = await api.post<{ access_token: string; profile: Profile }>("/api/auth/dev-login", { email });
    setDevToken(session.access_token);
    setProfile(session.profile);
  }

  async function logout() {
    // Local state is cleared unconditionally, even if the remote signOut
    // call fails or the Supabase project is unreachable — a user must
    // always be able to log out of THIS browser regardless of network state.
    try {
      if (config) {
        const supabase = getSupabaseClient(config.supabase_url, config.supabase_anon_key);
        if (supabase) await supabase.auth.signOut();
      }
    } catch {
      // ignore — still clear local state below
    }
    clearToken();
    setActiveToken(null);
    setProfile(null);
  }

  return (
    <AuthContext.Provider
      value={{
        profile,
        loading,
        config,
        configError,
        sendMagicLink,
        magicLinkStatus,
        magicLinkError,
        loginWithDevEmail,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
