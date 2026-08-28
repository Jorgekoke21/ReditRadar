import type { PromotionRisk as PromotionRiskType } from "../types";

const LABELS: Record<PromotionRiskType, string> = {
  low: "Riesgo bajo",
  medium: "Riesgo medio",
  high: "Riesgo alto",
};

const STYLES: Record<PromotionRiskType, string> = {
  low: "text-[#0A4638] bg-[#DCF7E3]",
  medium: "text-[#7a5b00] bg-[#FFF3D6]",
  high: "text-[#8a1f2b] bg-[#FBE1E3]",
};

export default function PromotionRiskBadge({ risk }: { risk: PromotionRiskType }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${STYLES[risk]}`}>
      {LABELS[risk]}
    </span>
  );
}
