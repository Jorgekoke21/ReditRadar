import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import MobileFilterSheet from "./MobileFilterSheet";

export interface ConversationFilters {
  q: string;
  state: string;
  minScore: string;
  subreddit: string;
  topicId: string;
  language: string;
  sort: "score" | "recent";
}

const STATE_OPTIONS = [
  ["", "Todos los estados"],
  ["recommended", "Recomendada"],
  ["saved", "Guardada"],
  ["responded", "Respondida"],
  ["discarded", "Descartada"],
];

const SCORE_OPTIONS = [
  ["", "Cualquier puntuación"],
  ["85", "85+ Responder ahora"],
  ["70", "70+ Revisar hoy"],
  ["55", "55+ Aportar valor"],
];

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-primary/60">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary focus:border-primary"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function FilterBar({
  filters,
  onChange,
  subreddits,
  topics,
}: {
  filters: ConversationFilters;
  onChange: (patch: Partial<ConversationFilters>) => void;
  subreddits: string[];
  topics: { id: string; name: string }[];
}) {
  const [sheetOpen, setSheetOpen] = useState(false);

  const controls = (
    <>
      <label className="flex flex-1 flex-col gap-1 text-xs text-primary/60 sm:min-w-[220px]">
        Buscar
        <input
          value={filters.q}
          onChange={(e) => onChange({ q: e.target.value })}
          placeholder="Buscar por título o resumen…"
          className="rounded-lg border border-primary/15 bg-white px-2.5 py-2 text-sm text-primary placeholder:text-primary/35 focus:border-primary"
        />
      </label>
      <Select label="Estado" value={filters.state} onChange={(v) => onChange({ state: v })} options={STATE_OPTIONS as [string, string][]} />
      <Select label="Puntuación mínima" value={filters.minScore} onChange={(v) => onChange({ minScore: v })} options={SCORE_OPTIONS as [string, string][]} />
      <Select
        label="Subreddit"
        value={filters.subreddit}
        onChange={(v) => onChange({ subreddit: v })}
        options={[["", "Todos"], ...subreddits.map((s) => [s, `r/${s}`] as [string, string])]}
      />
      <Select
        label="Tema"
        value={filters.topicId}
        onChange={(v) => onChange({ topicId: v })}
        options={[["", "Todos"], ...topics.map((t) => [t.id, t.name] as [string, string])]}
      />
      <Select
        label="Idioma"
        value={filters.language}
        onChange={(v) => onChange({ language: v })}
        options={[
          ["", "Todos"],
          ["es", "Español"],
          ["en", "English"],
        ]}
      />
      <Select
        label="Orden"
        value={filters.sort}
        onChange={(v) => onChange({ sort: v as "score" | "recent" })}
        options={[
          ["score", "Puntuación"],
          ["recent", "Más reciente"],
        ]}
      />
    </>
  );

  return (
    <div className="mb-4">
      <div className="hidden flex-wrap items-end gap-3 rounded-card border border-primary/10 bg-white p-3 md:flex">
        {controls}
      </div>

      <div className="flex items-center gap-2 md:hidden">
        <input
          value={filters.q}
          onChange={(e) => onChange({ q: e.target.value })}
          placeholder="Buscar…"
          className="min-h-[44px] flex-1 rounded-lg border border-primary/15 bg-white px-3 text-sm text-primary placeholder:text-primary/35"
        />
        <button
          onClick={() => setSheetOpen(true)}
          className="flex min-h-[44px] items-center gap-1.5 rounded-lg border border-primary/15 bg-white px-3 text-sm font-medium text-primary"
        >
          <SlidersHorizontal size={16} aria-hidden="true" />
          Filtros
        </button>
      </div>

      <MobileFilterSheet open={sheetOpen} onClose={() => setSheetOpen(false)}>
        <div className="flex flex-col gap-3">{controls}</div>
      </MobileFilterSheet>
    </div>
  );
}
