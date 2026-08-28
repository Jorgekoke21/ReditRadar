import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import ConversationRow from "../components/ConversationRow";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import FilterBar, { ConversationFilters } from "../components/FilterBar";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { ConversationListItem, Topic } from "../types";

const DEFAULT_FILTERS: ConversationFilters = {
  q: "",
  state: "",
  minScore: "",
  subreddit: "",
  topicId: "",
  language: "",
  sort: "score",
};

export default function Conversations() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<ConversationFilters>(DEFAULT_FILTERS);

  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.state) params.set("state", filters.state);
  if (filters.minScore) params.set("min_score", filters.minScore);
  if (filters.subreddit) params.set("subreddit", filters.subreddit);
  if (filters.topicId) params.set("topic_id", filters.topicId);
  if (filters.language) params.set("language", filters.language);
  params.set("sort", filters.sort);

  const conversationsQuery = useQuery({
    queryKey: ["conversations", filters],
    queryFn: () => api.get<ConversationListItem[]>(`/api/conversations?${params.toString()}`),
  });

  const topicsQuery = useQuery({ queryKey: ["topics"], queryFn: () => api.get<Topic[]>("/api/topics") });

  const allConversationsQuery = useQuery({
    queryKey: ["conversations", "all-for-filters"],
    queryFn: () => api.get<ConversationListItem[]>("/api/conversations"),
    staleTime: 60_000,
  });

  const subreddits = useMemo(
    () => Array.from(new Set((allConversationsQuery.data ?? []).map((c) => c.subreddit))).sort(),
    [allConversationsQuery.data]
  );

  async function handleSave(id: string) {
    await api.post(`/api/conversations/${id}/actions?action_type=saved`);
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
    toast.show("Guardada para más tarde");
  }

  async function handleDiscard(id: string) {
    await api.post(`/api/conversations/${id}/actions?action_type=discarded`);
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
    toast.show("Descartada", {
      actionLabel: "Deshacer",
      onAction: async () => {
        await api.post(`/api/conversations/${id}/actions?action_type=restored`);
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
      },
    });
  }

  const conversations = conversationsQuery.data ?? [];
  const hasActiveFilters = JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS);

  return (
    <div>
      <PageHeader title="Conversaciones" description="Todo lo detectado, filtrable por estado, puntuación, comunidad y tema." />

      <FilterBar filters={filters} onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))} subreddits={subreddits} topics={topicsQuery.data ?? []} />

      {conversationsQuery.isLoading && <LoadingState label="Cargando conversaciones…" />}
      {conversationsQuery.isError && (
        <ErrorState message="No se pudieron cargar las conversaciones." onRetry={() => conversationsQuery.refetch()} />
      )}
      {conversationsQuery.isSuccess && conversations.length === 0 && (
        <EmptyState
          title={hasActiveFilters ? "Ningún resultado con estos filtros" : "Todavía no hay conversaciones"}
          description={
            hasActiveFilters
              ? "Prueba a ampliar los filtros o el rango de puntuación."
              : "Importa una conversación manualmente o espera a la próxima revisión."
          }
          action={
            hasActiveFilters ? (
              <button
                onClick={() => setFilters(DEFAULT_FILTERS)}
                className="rounded-lg border border-primary/20 px-3.5 py-2 text-sm font-medium text-primary hover:bg-primary/5"
              >
                Quitar filtros
              </button>
            ) : undefined
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
