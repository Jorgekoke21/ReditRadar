import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useToast } from "../lib/toast";
import type { AlertDelivery, AlertSettings } from "../types";

export default function Alerts() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const settingsQuery = useQuery({ queryKey: ["alert-settings"], queryFn: () => api.get<AlertSettings>("/api/alerts/settings") });
  const previewQuery = useQuery({ queryKey: ["alert-preview"], queryFn: () => api.get<AlertDelivery[]>("/api/alerts/preview") });

  const [form, setForm] = useState<AlertSettings | null>(null);
  useEffect(() => {
    if (settingsQuery.data) setForm(settingsQuery.data);
  }, [settingsQuery.data]);

  const save = useMutation({
    mutationFn: (values: AlertSettings) => api.patch<AlertSettings>("/api/alerts/settings", values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alert-settings"] });
      toast.show("Configuración de alertas guardada");
    },
  });

  const sendTest = useMutation({
    mutationFn: () => api.post<{ sent_externally: boolean; provider: string }>("/api/alerts/send-test"),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["alert-preview"] });
      toast.show(
        r.sent_externally
          ? `Correo de prueba enviado vía ${r.provider}`
          : "Correo de prueba generado (sin proveedor externo, disponible abajo en la bandeja)"
      );
    },
  });

  if (settingsQuery.isLoading || !form) return <LoadingState label="Cargando configuración de alertas…" />;

  return (
    <div>
      <PageHeader title="Alertas" description="Resumen diario, alertas urgentes y previsualización de correos." />

      <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Correo destinatario
          <input
            value={form.email_recipient}
            onChange={(e) => setForm({ ...form, email_recipient: e.target.value })}
            placeholder="tu@email.com"
            className="min-h-[44px] max-w-sm rounded-lg border border-primary/15 px-3 text-sm text-primary placeholder:text-primary/35"
          />
        </label>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg bg-surface p-3">
            <label className="flex items-center gap-2 text-sm font-medium text-primary">
              <input
                type="checkbox"
                checked={form.daily_digest_enabled}
                onChange={(e) => setForm({ ...form, daily_digest_enabled: e.target.checked })}
              />
              Resumen diario
            </label>
            <div className="mt-2 flex items-center gap-2 text-xs text-primary/60">
              Hora
              <input
                type="time"
                value={form.daily_digest_time}
                onChange={(e) => setForm({ ...form, daily_digest_time: e.target.value })}
                className="rounded-lg border border-primary/15 px-2 py-1"
              />
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs text-primary/60">
              Puntuación mínima
              <input
                type="number"
                value={form.min_score_threshold}
                onChange={(e) => setForm({ ...form, min_score_threshold: Number(e.target.value) })}
                className="w-16 rounded-lg border border-primary/15 px-2 py-1"
              />
            </div>
          </div>

          <div className="rounded-lg bg-surface p-3">
            <label className="flex items-center gap-2 text-sm font-medium text-primary">
              <input
                type="checkbox"
                checked={form.urgent_alerts_enabled}
                onChange={(e) => setForm({ ...form, urgent_alerts_enabled: e.target.checked })}
              />
              Alertas urgentes
            </label>
            <div className="mt-2 flex items-center gap-2 text-xs text-primary/60">
              Umbral urgente
              <input
                type="number"
                value={form.urgent_score_threshold}
                onChange={(e) => setForm({ ...form, urgent_score_threshold: Number(e.target.value) })}
                className="w-16 rounded-lg border border-primary/15 px-2 py-1"
              />
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs text-primary/60">
              Máx. urgentes / día
              <input
                type="number"
                value={form.max_urgent_per_day}
                onChange={(e) => setForm({ ...form, max_urgent_per_day: Number(e.target.value) })}
                className="w-16 rounded-lg border border-primary/15 px-2 py-1"
              />
            </div>
          </div>
        </div>

        <label className="mt-3 flex items-center gap-2 text-sm font-medium text-primary">
          <input
            type="checkbox"
            checked={form.weekly_digest_enabled}
            onChange={(e) => setForm({ ...form, weekly_digest_enabled: e.target.checked })}
          />
          Resumen semanal
        </label>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => save.mutate(form)}
            className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-accent hover:bg-primary-hover"
          >
            Guardar configuración
          </button>
          <button
            onClick={() => sendTest.mutate()}
            className="rounded-lg border border-primary/20 px-3.5 py-2 text-sm font-medium text-primary hover:bg-primary/5"
          >
            Enviar correo de prueba
          </button>
        </div>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold text-primary">Bandeja de previsualización</h2>
      <p className="mb-3 text-sm text-primary/60">
        Sin un proveedor de correo externo configurado, los envíos se generan aquí en lugar de salir realmente.
      </p>

      {previewQuery.isLoading && <LoadingState label="Cargando previsualizaciones…" />}
      {previewQuery.data?.length === 0 && (
        <EmptyState title="Todavía no se ha generado ningún correo" description="Se mostrará aquí en cuanto se dispare un resumen o una alerta." />
      )}
      {previewQuery.data && previewQuery.data.length > 0 && (
        <div className="flex flex-col gap-2">
          {previewQuery.data.map((d) => (
            <details key={d.id} className="rounded-card border border-primary/10 bg-white p-3">
              <summary className="cursor-pointer text-sm">
                <span className="font-medium text-primary">{d.subject}</span>{" "}
                <span className="text-primary/50">
                  · {d.kind} · {formatDateTime(d.created_at)} · {d.sent ? "enviado" : "solo previsualización"}
                </span>
              </summary>
              <div className="mt-2 overflow-hidden rounded-lg border border-primary/10">
                <iframe title={d.subject} srcDoc={d.body_html} className="h-72 w-full bg-white" />
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
