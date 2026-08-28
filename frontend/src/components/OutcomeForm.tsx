import { useState } from "react";
import type { Outcome } from "../types";

const RESULT_OPTIONS: [string, string][] = [
  ["no_result", "Sin resultado todavía"],
  ["received_upvotes", "Recibió votos positivos"],
  ["author_replied", "El autor respondió"],
  ["conversation_started", "Se inició una conversación"],
  ["private_message_received", "Recibí un mensaje privado"],
  ["radarin_visit", "Visita a Radarin atribuida"],
  ["radarin_signup", "Registro en Radarin atribuido"],
  ["demo_requested", "Solicitó una demo"],
  ["customer", "Se convirtió en cliente"],
  ["removed", "El comentario fue eliminado"],
];

export default function OutcomeForm({
  outcome,
  onSubmit,
}: {
  outcome: Outcome | null;
  onSubmit: (values: {
    notes: string;
    upvotes: number | null;
    reply_count: number | null;
    attributed_visits: number | null;
    attributed_signups: number | null;
    result: string;
  }) => void;
}) {
  const [notes, setNotes] = useState(outcome?.notes ?? "");
  const [upvotes, setUpvotes] = useState(outcome?.upvotes?.toString() ?? "");
  const [replyCount, setReplyCount] = useState(outcome?.reply_count?.toString() ?? "");
  const [visits, setVisits] = useState(outcome?.attributed_visits?.toString() ?? "");
  const [signups, setSignups] = useState(outcome?.attributed_signups?.toString() ?? "");
  const [result, setResult] = useState(outcome?.result ?? "no_result");

  function numOrNull(v: string): number | null {
    return v.trim() === "" ? null : Number(v);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          notes,
          upvotes: numOrNull(upvotes),
          reply_count: numOrNull(replyCount),
          attributed_visits: numOrNull(visits),
          attributed_signups: numOrNull(signups),
          result,
        });
      }}
      className="flex flex-col gap-3"
    >
      <label className="flex flex-col gap-1 text-xs text-primary/60">
        Resultado
        <select
          value={result}
          onChange={(e) => setResult(e.target.value)}
          className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary"
        >
          {RESULT_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Votos
          <input
            type="number"
            value={upvotes}
            onChange={(e) => setUpvotes(e.target.value)}
            className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Respuestas
          <input
            type="number"
            value={replyCount}
            onChange={(e) => setReplyCount(e.target.value)}
            className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Visitas
          <input
            type="number"
            value={visits}
            onChange={(e) => setVisits(e.target.value)}
            className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Registros
          <input
            type="number"
            value={signups}
            onChange={(e) => setSignups(e.target.value)}
            className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-xs text-primary/60">
        Notas
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="rounded-lg border border-primary/15 bg-white p-2.5 text-sm text-primary"
        />
      </label>

      <button
        type="submit"
        className="self-start rounded-lg bg-primary px-3 py-2 text-sm font-medium text-accent hover:bg-primary-hover"
      >
        Guardar resultado
      </button>
    </form>
  );
}
