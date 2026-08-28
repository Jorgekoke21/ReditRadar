import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import SectionDisclosure from "../components/SectionDisclosure";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { Topic } from "../types";

interface TopicForm {
  name: string;
  description: string;
  languages: string;
  priority: "high" | "medium" | "low";
  is_active: boolean;
  keywords: string;
  exclusions: string;
  positive_examples: string;
  negative_examples: string;
}

function toForm(t: Topic): TopicForm {
  return {
    name: t.name,
    description: t.description,
    languages: t.languages,
    priority: t.priority,
    is_active: t.is_active,
    keywords: t.keywords.join(", "),
    exclusions: t.exclusions.join(", "),
    positive_examples: t.positive_examples.join("\n"),
    negative_examples: t.negative_examples.join("\n"),
  };
}

function toPayload(f: TopicForm) {
  return {
    name: f.name,
    description: f.description,
    languages: f.languages,
    priority: f.priority,
    is_active: f.is_active,
    keywords: f.keywords.split(",").map((s) => s.trim()).filter(Boolean),
    exclusions: f.exclusions.split(",").map((s) => s.trim()).filter(Boolean),
    positive_examples: f.positive_examples.split("\n").map((s) => s.trim()).filter(Boolean),
    negative_examples: f.negative_examples.split("\n").map((s) => s.trim()).filter(Boolean),
  };
}

const EMPTY_FORM: TopicForm = {
  name: "",
  description: "",
  languages: "es,en",
  priority: "medium",
  is_active: true,
  keywords: "",
  exclusions: "",
  positive_examples: "",
  negative_examples: "",
};

function TopicCard({ topic }: { topic: Topic }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<TopicForm>(toForm(topic));
  const [dirty, setDirty] = useState(false);

  const save = useMutation({
    mutationFn: () => api.patch<Topic>(`/api/topics/${topic.id}`, toPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["topics"] });
      toast.show("Tema actualizado");
      setDirty(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/api/topics/${topic.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["topics"] });
      toast.show("Tema eliminado");
    },
  });

  function update<K extends keyof TopicForm>(key: K, value: TopicForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  return (
    <div className="rounded-card border border-primary/10 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <input
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
          className="min-w-0 flex-1 border-none bg-transparent text-sm font-semibold text-primary outline-none"
        />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-primary/60">
            <input type="checkbox" checked={form.is_active} onChange={(e) => update("is_active", e.target.checked)} />
            Activo
          </label>
          <button onClick={() => remove.mutate()} aria-label="Eliminar tema" className="text-primary/40 hover:text-red-600">
            <Trash2 size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      <textarea
        value={form.description}
        onChange={(e) => update("description", e.target.value)}
        rows={2}
        placeholder="Descripción del tema"
        className="mt-1.5 w-full rounded-lg border border-primary/10 bg-surface p-2 text-xs text-primary/70"
      />

      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Prioridad
          <select value={form.priority} onChange={(e) => update("priority", e.target.value as TopicForm["priority"])} className="rounded-lg border border-primary/15 px-2 py-1.5 text-sm">
            <option value="high">Alta</option>
            <option value="medium">Media</option>
            <option value="low">Baja</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Idiomas
          <input value={form.languages} onChange={(e) => update("languages", e.target.value)} className="rounded-lg border border-primary/15 px-2.5 py-1.5 text-sm" />
        </label>
      </div>

      <label className="mt-3 flex flex-col gap-1 text-xs text-primary/60">
        Palabras y expresiones relacionadas (separadas por comas)
        <textarea value={form.keywords} onChange={(e) => update("keywords", e.target.value)} rows={2} className="rounded-lg border border-primary/15 p-2 text-sm" />
      </label>

      <SectionDisclosure title="Exclusiones y ejemplos">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            Palabras excluidas
            <textarea value={form.exclusions} onChange={(e) => update("exclusions", e.target.value)} rows={2} className="rounded-lg border border-primary/15 p-2 text-sm" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            Ejemplos positivos (uno por línea)
            <textarea value={form.positive_examples} onChange={(e) => update("positive_examples", e.target.value)} rows={2} className="rounded-lg border border-primary/15 p-2 text-sm" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            Ejemplos negativos (uno por línea)
            <textarea value={form.negative_examples} onChange={(e) => update("negative_examples", e.target.value)} rows={2} className="rounded-lg border border-primary/15 p-2 text-sm" />
          </label>
        </div>
      </SectionDisclosure>

      {dirty && (
        <button onClick={() => save.mutate()} className="mt-2 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-accent hover:bg-primary-hover">
          Guardar cambios
        </button>
      )}
    </div>
  );
}

export default function Topics() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [newForm, setNewForm] = useState<TopicForm>(EMPTY_FORM);

  const query = useQuery({ queryKey: ["topics"], queryFn: () => api.get<Topic[]>("/api/topics") });

  const create = useMutation({
    mutationFn: () => api.post<Topic>("/api/topics", toPayload(newForm)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["topics"] });
      toast.show("Tema creado");
      setShowForm(false);
      setNewForm(EMPTY_FORM);
    },
  });

  return (
    <div>
      <PageHeader
        title="Temas"
        description="Qué conversaciones vigilar: palabras clave, exclusiones y ejemplos."
        action={
          <button
            onClick={() => setShowForm((s) => !s)}
            className="flex min-h-[40px] items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-semibold text-accent hover:bg-primary-hover"
          >
            <Plus size={15} aria-hidden="true" />
            Nuevo tema
          </button>
        }
      />

      {showForm && (
        <div className="mb-4 rounded-card border border-primary/10 bg-white p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-1 flex-col gap-1 text-xs text-primary/60">
              Nombre del tema
              <input
                value={newForm.name}
                onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))}
                className="rounded-lg border border-primary/15 px-2.5 py-2 text-sm"
              />
            </label>
            <button
              onClick={() => create.mutate()}
              disabled={!newForm.name.trim() || create.isPending}
              className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-accent hover:bg-primary-hover disabled:opacity-60"
            >
              Crear
            </button>
          </div>
        </div>
      )}

      {query.isLoading && <LoadingState label="Cargando temas…" />}
      {query.isError && <ErrorState message="No se pudieron cargar los temas." onRetry={() => query.refetch()} />}
      {query.isSuccess && query.data.length === 0 && (
        <EmptyState title="Todavía no hay temas" description="Crea el primer tema que quieres vigilar." />
      )}
      {query.data && query.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {query.data.map((t) => (
            <TopicCard key={t.id} topic={t} />
          ))}
        </div>
      )}
    </div>
  );
}
