import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import OutcomeForm from "../components/OutcomeForm";
import PromotionRiskBadge from "../components/PromotionRisk";
import { ACTION_LABELS } from "../components/RecommendedAction";
import ReplyEditor from "../components/ReplyEditor";
import ScoreIndicator from "../components/ScoreIndicator";
import SectionDisclosure from "../components/SectionDisclosure";
import { api } from "../lib/api";
import { formatDateTime, timeAgo } from "../lib/format";
import { useToast } from "../lib/toast";
import type { ConversationDetail as ConversationDetailType } from "../types";

const MENTION_LABELS: Record<string, string> = {
  no: "No menciones Radarin en esta respuesta.",
  soft: "Puedes mencionar de forma suave que estás construyendo una herramienta.",
  transparent_direct: "Puedes mencionar Radarin directamente y de forma transparente.",
};

const SCORE_ROWS: [keyof NonNullable<ConversationDetailType["score_breakdown"]>, string, number][] = [
  ["audience_fit", "Encaje con el público objetivo", 25],
  ["problem_fit", "Problema relacionado con Radarin", 25],
  ["request_intent", "Solicita consejo o herramienta", 15],
  ["value_potential", "Podemos aportar una respuesta concreta", 15],
  ["recency", "Recencia", 10],
  ["low_competition", "Pocas respuestas todavía", 5],
  ["community_priority", "Prioridad de la comunidad", 5],
  ["promotion_risk_penalty", "Penalización por riesgo promocional", -20],
];

export default function ConversationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["conversation", id],
    queryFn: () => api.get<ConversationDetailType>(`/api/conversations/${id}`),
    enabled: !!id,
  });

  async function invalidate() {
    await queryClient.invalidateQueries({ queryKey: ["conversation", id] });
    await queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }

  async function handleMarkResponded() {
    await api.post(`/api/conversations/${id}/actions?action_type=marked_responded`);
    await invalidate();
    toast.show("Marcada como respondida");
  }

  async function handleSaveDraft(draftId: string, body: string) {
    await api.patch(`/api/conversations/${id}/drafts/${draftId}`, { body });
    await invalidate();
  }

  async function handleAnalyze() {
    await api.post(`/api/conversations/${id}/analyze`);
    await invalidate();
    toast.show("Conversación analizada");
  }

  async function handleRecalculate() {
    await api.post(`/api/conversations/${id}/recalculate`);
    await invalidate();
    toast.show("Puntuación recalculada");
  }

  async function handlePurgeNow() {
    await api.delete(`/api/conversations/${id}/raw-content`);
    await invalidate();
    toast.show("Contenido original eliminado");
  }

  async function handleOutcomeSubmit(values: {
    notes: string;
    upvotes: number | null;
    reply_count: number | null;
    attributed_visits: number | null;
    attributed_signups: number | null;
    result: string;
  }) {
    await api.post(`/api/conversations/${id}/outcome`, { ...values, final_text_used: "" });
    await invalidate();
    toast.show("Resultado guardado");
  }

  if (query.isLoading) return <LoadingState label="Cargando conversación…" />;
  if (query.isError || !query.data) return <ErrorState message="No se pudo cargar la conversación." onRetry={() => query.refetch()} />;

  const c = query.data;

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="mb-4 flex items-center gap-1.5 text-sm font-medium text-primary/60 hover:text-primary"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        Volver
      </button>

      <div className="mb-5 flex items-start gap-4">
        <ScoreIndicator score={c.score_total ?? 0} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 text-xs uppercase tracking-wide text-primary/50">
            <span>r/{c.subreddit}</span>
            <span aria-hidden="true">·</span>
            <span>{timeAgo(c.published_at || c.detected_at)}</span>
            {c.is_demo && <span className="rounded-full bg-primary/5 px-1.5 py-0.5 normal-case tracking-normal">Ejemplo ficticio</span>}
          </div>
          <h1 className="mt-0.5 text-lg font-semibold leading-snug text-primary">{c.title}</h1>
        </div>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        <button
          onClick={handleMarkResponded}
          className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-accent hover:bg-primary-hover"
        >
          Marcar como respondida
        </button>
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-primary/20 px-3.5 py-2 text-sm font-medium text-primary hover:bg-primary/5"
          >
            <ExternalLink size={15} aria-hidden="true" />
            Abrir en Reddit
          </a>
        )}
      </div>

      <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-primary/40">Qué necesita la persona</p>
            <p className="mt-1 text-sm text-primary">{c.problem_detected || "—"}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-primary/40">Cómo podemos aportar</p>
            <p className="mt-1 text-sm text-primary">{c.analysis?.value_angle || "—"}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-primary/40">Acción recomendada</p>
            <p className="mt-1 text-sm font-medium text-primary">
              {c.recommended_action ? ACTION_LABELS[c.recommended_action] : "—"}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-primary/40">Mención de Radarin</p>
            <div className="mt-1 flex items-center gap-2">
              {c.promotion_risk && <PromotionRiskBadge risk={c.promotion_risk} />}
              <p className="text-sm text-primary">{c.analysis ? MENTION_LABELS[c.analysis.mention_radarin] : "—"}</p>
            </div>
          </div>
        </div>

        <div className="mt-5 border-t border-primary/10 pt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-primary/40">Borrador de respuesta</p>
          <ReplyEditor drafts={c.drafts} onSaveEdit={handleSaveDraft} />
        </div>
      </div>

      <div className="mt-4 rounded-card border border-primary/10 bg-white px-4 sm:px-5">
        <SectionDisclosure title="Conversación original">
          {c.raw_purged ? (
            <p className="text-sm text-primary/50">
              El contenido original se eliminó automáticamente (retención de 48h) o manualmente. Se conservan la
              puntuación, el resumen y el resultado.
            </p>
          ) : (
            <div>
              <p className="whitespace-pre-wrap text-sm text-primary">{c.raw_body || "(sin texto)"}</p>
              <button
                onClick={handlePurgeNow}
                className="mt-3 flex items-center gap-1.5 text-sm font-medium text-red-600 hover:underline"
              >
                <Trash2 size={14} aria-hidden="true" />
                Eliminar contenido original ahora
              </button>
              {c.expires_at && (
                <p className="mt-1 text-xs text-primary/40">Expira automáticamente: {formatDateTime(c.expires_at)}</p>
              )}
            </div>
          )}
        </SectionDisclosure>

        <SectionDisclosure title="Desglose de puntuación">
          {(() => {
            const breakdown = c.score_breakdown;
            if (!breakdown) {
              return <p className="text-sm text-primary/50">Todavía no se ha analizado esta conversación.</p>;
            }
            return (
              <div className="flex flex-col gap-1.5">
                {SCORE_ROWS.map(([key, label, max]) => (
                  <div key={key} className="flex items-center justify-between text-sm">
                    <span className="text-primary/60">
                      {label} <span className="text-primary/35">(máx {max})</span>
                    </span>
                    <span className="font-medium text-primary">
                      {key === "promotion_risk_penalty" ? "-" : ""}
                      {breakdown[key]}
                    </span>
                  </div>
                ))}
                <div className="mt-2 flex items-center justify-between border-t border-primary/10 pt-2 text-sm font-semibold text-primary">
                  <span>Total</span>
                  <span>{breakdown.total} / 100</span>
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={handleRecalculate}
                    className="flex items-center gap-1.5 rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/5"
                  >
                    <RefreshCw size={13} aria-hidden="true" />
                    Recalcular puntuación
                  </button>
                  <button
                    onClick={handleAnalyze}
                    className="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/5"
                  >
                    Volver a analizar
                  </button>
                </div>
              </div>
            );
          })()}
        </SectionDisclosure>

        <SectionDisclosure title="Normas y notas de la comunidad">
          <p className="text-sm text-primary/70">{c.community_notes || "Sin notas registradas todavía."}</p>
          {c.community_rules_url && (
            <a href={c.community_rules_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-sm text-primary underline">
              Ver reglas del subreddit
            </a>
          )}
        </SectionDisclosure>

        <SectionDisclosure title="Resultado">
          <OutcomeForm outcome={c.outcome} onSubmit={handleOutcomeSubmit} />
        </SectionDisclosure>
      </div>
    </div>
  );
}
