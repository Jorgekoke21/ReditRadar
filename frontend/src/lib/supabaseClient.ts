import { createClient, SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;
let clientKey = "";

/**
 * Lazily creates (and caches) a Supabase client for a given url/anonKey pair.
 * The pair comes from the backend's public GET /api/auth/config, not from
 * Vite env vars directly — the backend is the single source of truth for
 * which Supabase project is active, so the frontend never has to be
 * redeployed just because that changed.
 */
export function getSupabaseClient(url: string, anonKey: string): SupabaseClient | null {
  if (!url || !anonKey) return null;
  const key = `${url}::${anonKey}`;
  if (client && clientKey === key) return client;
  client = createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  clientKey = key;
  return client;
}
