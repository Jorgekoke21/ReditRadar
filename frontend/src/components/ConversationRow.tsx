import { Bookmark, ExternalLink, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { timeAgo } from "../lib/format";
import type { ConversationListItem } from "../types";
import PromotionRiskBadge from "./PromotionRisk";
import RecommendedActionLabel from "./RecommendedAction";
import ScoreIndicator from "./ScoreIndicator";

const STATE_LABELS: Record<string, string> = {
  new: "Nueva",
  recommended: "Nueva",
  review: "Revisada",
  saved: "Guardada",
  responded: "Respondida",
  discarded: "Descartada",
  expired: "Expirada",
};

export default function ConversationRow({
  conversation,
  onSave,
  onDiscard,
}: {
  conversation: ConversationListItem;
  onSave?: () => void;
  onDiscard?: () => void;
}) {
  const navigate = useNavigate();
  const c = conversation;

  return (
    <div className="flex items-start gap-3 border-b border-primary/10 bg-white px-3 py-3.5 last:border-b-0 sm:px-4">
      <ScoreIndicator score={c.score_total ?? 0} />

      <button
        onClick={() => navigate(`/conversations/${c.id}`)}
        className="min-w-0 flex-1 text-left"
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] tracking-wide text-primary/50">
          <span>r/{c.subreddit}</span>
          <span aria-hidden="true">·</span>
          <span className="uppercase">{timeAgo(c.published_at || c.detected_at)}</span>
          {c.is_demo && (
            <span className="rounded-full bg-primary/5 px-1.5 py-0.5 text-primary/50">Ejemplo ficticio</span>
          )}
        </div>
        <p className="mt-0.5 truncate text-[15px] font-medium text-primary">{c.title}</p>
        <p className="mt-0.5 line-clamp-1 text-sm text-primary/60">{c.summary || c.problem_detected}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {c.recommended_action && <RecommendedActionLabel action={c.recommended_action} />}
          {c.promotion_risk && <PromotionRiskBadge risk={c.promotion_risk} />}
          {c.topic_name && <span className="text-[12px] text-primary/40">{c.topic_name}</span>}
        </div>
      </button>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <span className="text-[11px] font-medium text-primary/40">{STATE_LABELS[c.state]}</span>
        <div className="flex items-center gap-1">
          {c.url && (
            <a
              href={c.url}
              target="_blank"
              rel="noreferrer"
              title="Abrir en Reddit"
              aria-label="Abrir en Reddit"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-primary/50 hover:bg-primary/5 hover:text-primary"
            >
              <ExternalLink size={16} aria-hidden="true" />
            </a>
          )}
          {onSave && (
            <button
              onClick={onSave}
              title="Guardar"
              aria-label="Guardar"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-primary/50 hover:bg-primary/5 hover:text-primary"
            >
              <Bookmark size={16} aria-hidden="true" />
            </button>
          )}
          {onDiscard && (
            <button
              onClick={onDiscard}
              title="Descartar"
              aria-label="Descartar"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-primary/50 hover:bg-primary/5 hover:text-red-600"
            >
              <X size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
