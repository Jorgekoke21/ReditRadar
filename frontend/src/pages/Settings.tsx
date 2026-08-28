import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Link2, Unlink } from "lucide-react";
import { useState } from "react";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import type { Community, ConversationListItem, IntegrationsStatus, Topic } from "../types";

function StatusRow({ label, value, tone }: { label: string; value: string; tone: "on" | "off" | "neutral" }) {
  const dot = tone === "on" ? "bg-emerald-500" : tone === "off" ? "bg-primary/25" : "bg-amber-500";
  return (
    <div className="flex items-center justify-between border-b border-primary/10 py-2.5 text-sm last:border-b-0">
      <span className="text-primary/70">{label}</span>
      <span className="flex items-center gap-2 font-medium text-primary">
        <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
        {value}
      </span>
    </div>
  );
}

const REDDIT_STATE_KEY = "radarin_reddit_oauth_state";

export default function Settings() {
  const { profile } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const query = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<IntegrationsStatus>("/api/settings/integrations") });

  async function handleConnectReddit() {
    setBusy(true);
    try {
      const { authorize_url, state } = await api.get<{ authorize_url: string; state: string }>(
        "/api/reddit/connect"
      );
      // Kept so the callback page can compare before spending the code; the
      // backend validates the same state against its own record regardless.
      sessionStorage.setItem(REDDIT_STATE_KEY, state);
      window.location.href = authorize_url;
    } catch (err) {
      setBusy(false);
      toast.show(err instanceof Error ? err.message : "No se pudo iniciar la conexión con Reddit");
    }
  }

  async function handleDisconnectReddit() {
    setBusy(true);
    try {
      await api.delete("/api/reddit/connection");
      await queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast.show("Reddit desconectado");
    } catch (err) {
      toast.show(err instanceof Error ? err.message : "No se pudo desconectar Reddit");
    } finally {
      setBusy(false);
    }
  }

  async function handleExport() {
    const [conversations, communities, topics] = await Promise.all([
      api.get<ConversationListItem[]>("/api/conversations"),
      api.get<Community[]>("/api/communities"),
      api.get<Topic[]>("/api/topics"),
    ]);
    const blob = new Blob([JSON.stringify({ conversations, communities, topics }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `radar-conversaciones-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (query.isLoading || !query.data) return <LoadingState label="Cargando configuración…" />;
  const s = query.data;

  return (
    <div>
      <PageHeader title="Configuración" description="Estado de integraciones, cuenta, retención y privacidad." />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-1 text-sm font-semibold text-primary">Integraciones</h2>
          <StatusRow
            label="API oficial de Reddit"
            value={
              s.reddit_api_enabled
                ? s.reddit_connected
                  ? "Reddit conectado"
                  : "Reddit no conectado"
                : "Desactivada"
            }
            tone={s.reddit_api_enabled && s.reddit_connected ? "on" : "off"}
          />
          {s.reddit_api_enabled && (
            <div className="pt-3">
              {s.reddit_connected ? (
                <button
                  onClick={handleDisconnectReddit}
                  disabled={busy}
                  data-testid="reddit-disconnect"
                  className="flex items-center gap-1.5 rounded-lg border border-primary/20 px-3.5 py-2 text-sm font-medium text-primary hover:bg-primary/5 disabled:opacity-50"
                >
                  <Unlink size={15} aria-hidden="true" />
                  Desconectar
                </button>
              ) : (
                <button
                  onClick={handleConnectReddit}
                  disabled={busy}
                  data-testid="reddit-connect"
                  className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  <Link2 size={15} aria-hidden="true" />
                  Conectar Reddit
                </button>
              )}
              <p className="mt-2 text-xs leading-relaxed text-primary/50">
                Acceso de solo lectura. ReditRadar nunca publica, vota ni envía mensajes en tu nombre.
              </p>
            </div>
          )}
          <StatusRow
            label="Análisis con IA"
            value={s.ai_analysis_enabled ? `Activo (${s.ai_provider})` : "Desactivado — usando reglas deterministas"}
            tone={s.ai_analysis_enabled ? "on" : "off"}
          />
          <StatusRow
            label="Correo"
            value={s.email_configured ? `Configurado (${s.email_provider})` : "Sin configurar — modo previsualización"}
            tone={s.email_configured ? "on" : "neutral"}
          />
          <StatusRow
            label="Modo de autenticación"
            value={s.auth_mode === "supabase" ? "Supabase Auth (AUTH_MODE=supabase)" : "Desarrollo (AUTH_MODE=development)"}
            tone={s.auth_mode === "supabase" ? "on" : "neutral"}
          />
          <StatusRow
            label="Proyecto Supabase"
            value={s.supabase_configured ? "Configurado" : "Sin configurar"}
            tone={s.supabase_configured ? "on" : "neutral"}
          />
        </div>

        <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-1 text-sm font-semibold text-primary">Retención y privacidad</h2>
          <StatusRow label="Retención de contenido original" value={`${s.raw_content_retention_hours} horas`} tone="neutral" />
          <p className="mt-3 text-sm leading-relaxed text-primary/60">
            El título, el cuerpo y el autor de cada conversación se eliminan automáticamente pasado este plazo (o al
            instante desde la ficha de la conversación). La puntuación, el resumen operativo y el resultado se
            conservan para las métricas del historial.
          </p>
        </div>

        <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-1 text-sm font-semibold text-primary">Cuenta</h2>
          <StatusRow label="Correo" value={profile?.email ?? "—"} tone="neutral" />
          <StatusRow label="Cuenta" value={profile?.account_id.slice(0, 8) ?? "—"} tone="neutral" />
        </div>

        <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-1 text-sm font-semibold text-primary">Exportación de datos</h2>
          <p className="mb-3 text-sm text-primary/60">
            Descarga tus conversaciones, comunidades y temas en formato JSON.
          </p>
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-primary/20 px-3.5 py-2 text-sm font-medium text-primary hover:bg-primary/5"
          >
            <Download size={15} aria-hidden="true" />
            Exportar mis datos
          </button>
        </div>
      </div>
    </div>
  );
}
