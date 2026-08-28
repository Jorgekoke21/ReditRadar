import type { RecommendedAction as RecommendedActionType } from "../types";

export const ACTION_LABELS: Record<RecommendedActionType, string> = {
  respond_now: "Responder ahora",
  review_today: "Revisar hoy",
  help_without_mentioning: "Aportar sin mencionar Radarin",
  ask_question: "Preguntar antes de responder",
  observe: "Observar",
  discard: "Descartar",
};

export default function RecommendedActionLabel({ action }: { action: RecommendedActionType }) {
  const strong = action === "respond_now";
  return (
    <span className={`text-[13px] ${strong ? "font-semibold text-primary" : "text-primary/70"}`}>
      {ACTION_LABELS[action]}
    </span>
  );
}
