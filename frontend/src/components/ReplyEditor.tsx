import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import type { Draft } from "../types";
import { useToast } from "../lib/toast";

const VARIANT_LABELS: Record<Draft["variant"], string> = {
  educational: "Educativo (sin mencionar Radarin)",
  soft_mention: "Mención suave",
  direct_transparent: "Mención directa y transparente",
};

export default function ReplyEditor({
  drafts,
  onSaveEdit,
}: {
  drafts: Draft[];
  onSaveEdit: (draftId: string, body: string) => void;
}) {
  const toast = useToast();
  const recommended = drafts.find((d) => d.is_recommended) ?? drafts[0];
  const [activeId, setActiveId] = useState(recommended?.id);
  const [showOthers, setShowOthers] = useState(false);
  const [body, setBody] = useState(recommended?.body ?? "");
  const [copied, setCopied] = useState(false);

  const active = drafts.find((d) => d.id === activeId) ?? recommended;

  useEffect(() => {
    setBody(active?.body ?? "");
    setCopied(false);
  }, [active?.id]);

  if (!drafts.length || !active) {
    return <p className="text-sm text-primary/50">Todavía no hay un borrador para esta conversación.</p>;
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(body);
    setCopied(true);
    toast.show("Respuesta copiada al portapapeles");
    setTimeout(() => setCopied(false), 2000);
  }

  function handleBlurSave() {
    if (active && body !== active.body) {
      onSaveEdit(active.id, body);
    }
  }

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-primary/40">
        {VARIANT_LABELS[active.variant]}
      </p>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onBlur={handleBlurSave}
        rows={6}
        className="w-full resize-y rounded-lg border border-primary/15 bg-white p-3 text-sm leading-relaxed text-primary focus:border-primary"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-accent hover:bg-primary-hover"
        >
          {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {copied ? "Copiado" : "Copiar respuesta"}
        </button>
        {drafts.length > 1 && (
          <button
            onClick={() => setShowOthers((s) => !s)}
            className="text-sm font-medium text-primary/60 hover:text-primary"
          >
            {showOthers ? "Ocultar otras versiones" : "Ver otras versiones"}
          </button>
        )}
      </div>

      {showOthers && (
        <div className="mt-3 flex flex-wrap gap-2">
          {drafts.map((d) => (
            <button
              key={d.id}
              onClick={() => setActiveId(d.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                d.id === active.id ? "bg-primary text-accent" : "bg-surface text-primary/60 hover:bg-primary/10"
              }`}
            >
              {VARIANT_LABELS[d.variant]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
