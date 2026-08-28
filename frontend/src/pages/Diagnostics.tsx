import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useToast } from "../lib/toast";
import type { IntegrationsStatus, JobDiagnostics, JobRun } from "../types";

const JOBS = [
  "fetch_reddit_conversations",
  "analyze_pending_conversations",
  "recalculate_scores",
  "send_urgent_alerts",
  "send_daily_digest",
  "send_weekly_digest",
  "purge_expired_reddit_content",
  "sync_deleted_reddit_content",
];

const STATUS_STYLES: Record<string, string> = {
  success: "text-emerald-700 bg-emerald-50",
  failed: "text-red-700 bg-red-50",
  running: "text-amber-700 bg-amber-50",
};

export default function Diagnostics() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["jobs"], queryFn: () => api.get<JobRun[]>("/api/jobs") });
  const diagnosticsQuery = useQuery({
    queryKey: ["job-diagnostics"],
    queryFn: () => api.get<JobDiagnostics>("/api/jobs/diagnostics"),
  });
  const integrationsQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.get<IntegrationsStatus>("/api/settings/integrations"),
  });

  const runJob = useMutation({
    mutationFn: (jobName: string) => api.post(`/api/jobs/${jobName}/run`),
    onSuccess: (_data, jobName) => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["job-diagnostics"] });
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast.show(`Ejecutado: ${jobName}`);
    },
    onError: () => toast.show("No se pudo ejecutar el job"),
  });

  return (
    <div>
      <PageHeader title="Diagnóstico de jobs" description="Ejecución manual y registro de las tareas programadas." />

      {integrationsQuery.data && (
        <div className="mb-5 grid gap-3 md:grid-cols-2">
          <section className="rounded-card border border-primary/10 bg-white p-4" aria-label="Estado de Reddit">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-primary">Reddit</h2>
              <span className={"rounded-full px-2 py-0.5 text-xs font-medium " + (integrationsQuery.data.reddit_api_enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600")}>
                {integrationsQuery.data.reddit_api_enabled ? "activada" : "desactivada"}
              </span>
            </div>
            <p className="mt-2 text-xs text-primary/60">
              Credenciales: {integrationsQuery.data.reddit_credentials_configured ? "configuradas" : "no configuradas"} - OAuth: {integrationsQuery.data.reddit_connected ? "conectado" : "sin conectar"}
            </p>
            <p className="mt-1 text-xs text-primary/60">
              Comunidades: {integrationsQuery.data.reddit_communities_reviewed} - posts: {integrationsQuery.data.reddit_posts_retrieved} - nuevas: {integrationsQuery.data.reddit_new_conversations} - duplicadas: {integrationsQuery.data.reddit_duplicates}
            </p>
            <p className="mt-1 text-xs text-primary/60">
              Errores: {integrationsQuery.data.reddit_errors} - cuota restante: {integrationsQuery.data.reddit_rate_remaining ?? "desconocida"} - usada: {integrationsQuery.data.reddit_rate_used ?? "desconocida"} - reset: {integrationsQuery.data.reddit_rate_reset_seconds ?? "desconocido"}s
            </p>
            <p className="mt-1 text-xs text-primary/50">
              Siguiente fetch: {integrationsQuery.data.reddit_next_run_frequency} (hora concreta en logs del worker)
            </p>
            <p className="mt-1 text-xs text-primary/50">
              Ultima ejecucion: {integrationsQuery.data.reddit_last_run_at ? formatDateTime(integrationsQuery.data.reddit_last_run_at) : "sin ejecuciones"} - correcta: {integrationsQuery.data.reddit_last_success ? "si" : "no"}
            </p>
          </section>
          <section className="rounded-card border border-primary/10 bg-white p-4" aria-label="Estado del worker">
            <h2 className="text-sm font-semibold text-primary">Worker</h2>
            <p className="mt-2 text-xs text-primary/60">
              Scheduler: {diagnosticsQuery.data?.worker.scheduler_managed ? "APScheduler independiente" : "no disponible"}
            </p>
            <p className="mt-1 text-xs text-primary/60">
              Jobs registrados: {diagnosticsQuery.data?.registered_jobs.length ?? "-"} - siguiente ejecución según la frecuencia configurada
            </p>
            <p className="mt-1 text-xs text-primary/50">
              Fetch Reddit: {diagnosticsQuery.data?.frequencies.fetch_reddit_conversations ?? "no disponible"}
            </p>
          </section>
        </div>
      )}

      <div className="mb-5 flex flex-wrap gap-2">
        {JOBS.map((job) => (
          <button
            key={job}
            onClick={() => runJob.mutate(job)}
            disabled={runJob.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-primary/20 bg-white px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/5 disabled:opacity-50"
          >
            <Play size={12} aria-hidden="true" />
            {job}
          </button>
        ))}
      </div>

      {query.isLoading && <LoadingState label="Cargando historial de jobs…" />}
      {query.data?.length === 0 && <EmptyState title="Todavía no se ha ejecutado ningún job" />}
      {query.data && query.data.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-primary/10 bg-white">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-primary/10 text-left text-xs uppercase tracking-wide text-primary/40">
                <th className="px-3 py-2">Job</th>
                <th className="px-3 py-2">Estado</th>
                <th className="px-3 py-2">Procesados</th>
                <th className="px-3 py-2">Errores</th>
                <th className="px-3 py-2">Duración</th>
                <th className="px-3 py-2">Inicio</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((run) => (
                <tr key={run.id} className="border-b border-primary/5 last:border-b-0">
                  <td className="px-3 py-2 font-medium text-primary">{run.job_name}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[run.status] ?? ""}`}>
                      {run.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-primary/70">{run.processed_count}</td>
                  <td className="px-3 py-2 text-primary/70">{run.error_count}</td>
                  <td className="px-3 py-2 text-primary/70">{run.duration_ms ?? "—"} ms</td>
                  <td className="px-3 py-2 text-primary/50">{formatDateTime(run.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
