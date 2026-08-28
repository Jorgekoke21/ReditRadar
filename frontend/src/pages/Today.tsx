import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import ConversationRow from "../components/ConversationRow";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { ConversationListItem, Dashboard } from "../types";

export default function Today() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [reviewing, setReviewing] = useState(false);

  const dashboardQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("/api/dashboard"),
  });

  const conversationsQuery = useQuery({
    queryKey: ["conversations", { sort: "score" }],
    queryFn: () => api.get<ConversationListItem[]>("/api/conversations?sort=score"),
  });

  async function handleReviewNow() {
    setReviewing(true);
    try {
      await api.post("/api/jobs/analyze_pending_conversations/run");
      await api.post("/api/jobs/recalculate_scores/run");
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
      toast.show("Revisión completada");
    } catch {
      toast.show("No se pudo completar la revisión");
    } finally {
      setReviewing(false);
    }
  }

  async function handleSave(id: string) {
    await api.post(`/api/conversations/${id}/actions?action_type=saved`);
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    toast.show("Guardada para más tarde");
  }

  async function handleDiscard(id: string) {
    await api.post(`/api/conversations/${id}/actions?action_type=discarded`);
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    toast.show("Descartada", {
      actionLabel: "Deshacer",
      onAction: async () => {
        await api.post(`/api/conversations/${id}/actions?action_type=restored`);
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
        queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      },
    });
  }

  const conversations = (conversationsQuery.data ?? []).filter(
    (c) => c.state !== "discarded" && c.state !== "responded"
  );

  return (
    <div>
      <PageHeader
        title="Hoy"
        description={
          dashboardQuery.data
            ? `${dashboardQuery.data.found_today} nuevas hoy · ${conversations.length} pendientes de revisar en total`
            : "Conversaciones encontradas hoy"
        }
        action={
          <button
            onClick={handleReviewNow}
            disabled={reviewing}
            className="flex min-h-[40px] items-center gap-2 rounded-lg bg-primary px-3.5 text-sm font-semibold text-accent hover:bg-primary-hover disabled:opacity-60"
          >
            <RefreshCw size={15} className={reviewing ? "animate-spin" : ""} aria-hidden="true" />
            {reviewing ? "Revisando…" : "Revisar ahora"}
          </button>
        }
      />

      {dashboardQuery.data && (
        <div className="mb-5 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span className="text-primary">
            <strong className="font-semibold">{dashboardQuery.data.respond_now}</strong>{" "}
            <span className="text-primary/60">responder ahora</span>
          </span>
          <span className="text-primary">
            <strong className="font-semibold">{dashboardQuery.data.review_today}</strong>{" "}
            <span className="text-primary/60">revisar hoy</span>
          </span>
          <span className="text-primary">
            <strong className="font-semibold">{dashboardQuery.data.saved}</strong>{" "}
            <span className="text-primary/60">guardadas</span>
          </span>
        </div>
      )}

      {conversationsQuery.isLoading && <LoadingState label="Cargando conversaciones…" />}
      {conversationsQuery.isError && (
        <ErrorState message="No se pudieron cargar las conversaciones." onRetry={() => conversationsQuery.refetch()} />
      )}
      {conversationsQuery.isSuccess && conversations.length === 0 && (
        <EmptyState
          title="No hemos encontrado conversaciones relevantes todavía"
          description="Puedes importar una conversación manualmente, revisar los temas vigilados o cargar datos de demostración desde Configuración."
          action={
            <a
              href="/manual-import"
              className="rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-accent hover:bg-primary-hover"
            >
              Importar conversación
            </a>
          }
        />
      )}
      {conversations.length > 0 && (
        <div className="overflow-hidden rounded-card border border-primary/10">
          {conversations.map((c) => (
            <ConversationRow key={c.id} conversation={c} onSave={() => handleSave(c.id)} onDiscard={() => handleDiscard(c.id)} />
          ))}
        </div>
      )}
    </div>
  );
}
