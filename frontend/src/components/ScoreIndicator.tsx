function tone(score: number) {
  if (score >= 85) return { ring: "#062F25", text: "#062F25", bg: "#A3FF12" };
  if (score >= 70) return { ring: "#0A4638", text: "#0A4638", bg: "#DCF7E3" };
  if (score >= 55) return { ring: "#4a5a56", text: "#33403c", bg: "#E7EEEC" };
  return { ring: "#8a938f", text: "#6b7572", bg: "#F1F8F5" };
}

export default function ScoreIndicator({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const t = tone(score);
  const dims = size === "sm" ? "h-8 w-8 text-[11px]" : "h-10 w-10 text-xs";
  return (
    <div
      className={`flex ${dims} shrink-0 items-center justify-center rounded-full font-semibold`}
      style={{ backgroundColor: t.bg, color: t.text, border: `1.5px solid ${t.ring}33` }}
      aria-label={`Puntuación ${score} de 100`}
      title={`Puntuación: ${score}/100`}
    >
      {score}
    </div>
  );
}
