import { useQuery } from "@tanstack/react-query";
import ConversationRow from "../components/ConversationRow";
import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import { api } from "../lib/api";
import type { HistoryData } from "../types";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-card border border-primary/10 bg-white px-4 py-3">
      <p className="text-lg font-semibold text-primary">{value}</p>
      <p className="text-xs text-primary/50">{label}</p>
    </div>
  );
}

export default function History() {
  const query = useQuery({ queryKey: ["history"], queryFn: () => api.get<HistoryData>("/api/history") });

  if (query.isLoading) return <LoadingState label="Cargando historial…" />;
  if (!query.data) return null;

  const h = query.data;

  return (
    <div>
      <PageHeader title="Historial" description="Conversaciones respondidas y resultados obtenidos." />

      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Puntuación media" value={h.average_score} />
        <Stat label="Conversaciones iniciadas" value={h.conversations_started} />
        <Stat label="Visitas atribuidas" value={h.attributed_visits} />
        <Stat label="Registros atribuidos" value={h.attributed_signups} />
      </div>

      <div className="mb-5 grid gap-4 sm:grid-cols-2">
        <div className="rounded-card border border-primary/10 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-primary">Comunidades más útiles</h2>
          {h.best_communities.length === 0 ? (
            <p className="text-sm text-primary/50">Todavía no hay respuestas registradas.</p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-sm">
              {h.best_communities.map((c) => (
                <li key={c.name} className="flex justify-between text-primary/80">
                  <span>r/{c.name}</span>
                  <span className="text-primary/50">{c.responses_made} respuestas</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-card border border-primary/10 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-primary">Temas más frecuentes</h2>
          {h.top_topics.length === 0 ? (
            <p className="text-sm text-primary/50">Todavía no hay suficientes datos.</p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-sm">
              {h.top_topics.map((t) => (
                <li key={t.name} className="flex justify-between text-primary/80">
                  <span>{t.name}</span>
                  <span className="text-primary/50">{t.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <h2 className="mb-2 text-sm font-semibold text-primary">Conversaciones respondidas</h2>
      {h.responded_conversations.length === 0 ? (
        <EmptyState title="Todavía no has respondido a ninguna conversación" description="Cuando marques una como respondida aparecerá aquí." />
      ) : (
        <div className="overflow-hidden rounded-card border border-primary/10">
          {h.responded_conversations.map((c) => (
            <ConversationRow key={c.id} conversation={c} />
          ))}
        </div>
      )}
    </div>
  );
}
