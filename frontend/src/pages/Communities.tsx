import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import PageHeader from "../components/PageHeader";
import SectionDisclosure from "../components/SectionDisclosure";
import { api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { Community } from "../types";

type CommunityForm = Omit<Community, "id" | "opportunities_found" | "responses_made" | "historical_outcome" | "rules_last_reviewed_at"> & {
  rules_last_reviewed_at: string;
};

const EMPTY_FORM: CommunityForm = {
  name: "",
  is_active: true,
  group: "leads",
  priority: "medium",
  primary_language: "en",
  allows_links: "unknown",
  allows_self_promo: "unknown",
  notes: "",
  rules_url: "",
  rules_last_reviewed_at: "",
};

function CommunityCard({ community }: { community: Community }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<CommunityForm>({
    ...community,
    rules_last_reviewed_at: community.rules_last_reviewed_at ?? "",
  });
  const [dirty, setDirty] = useState(false);

  const save = useMutation({
    mutationFn: (patch: Partial<Community>) => api.patch<Community>(`/api/communities/${community.id}`, { ...form, ...patch }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["communities"] });
      toast.show("Comunidad actualizada");
      setDirty(false);
    },
  });

  function update<K extends keyof CommunityForm>(key: K, value: CommunityForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  return (
    <div className="rounded-card border border-primary/10 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-primary">r/{community.name}</p>
          <p className="text-xs text-primary/50">
            {community.opportunities_found} oportunidades · {community.responses_made} respuestas
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-primary/60">
          <input type="checkbox" checked={form.is_active} onChange={(e) => update("is_active", e.target.checked)} />
          Activa
        </label>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Grupo
          <select value={form.group} onChange={(e) => update("group", e.target.value)} className="min-w-0 rounded-lg border border-primary/15 px-2 py-1.5 text-sm">
            <option value="leads">Clientes potenciales</option>
            <option value="learning">Aprendizaje</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Prioridad
          <select value={form.priority} onChange={(e) => update("priority", e.target.value as Community["priority"])} className="min-w-0 rounded-lg border border-primary/15 px-2 py-1.5 text-sm">
            <option value="high">Alta</option>
            <option value="medium">Media</option>
            <option value="low">Baja</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Enlaces permitidos
          <select value={form.allows_links} onChange={(e) => update("allows_links", e.target.value as Community["allows_links"])} className="min-w-0 rounded-lg border border-primary/15 px-2 py-1.5 text-sm">
            <option value="yes">Sí</option>
            <option value="no">No</option>
            <option value="unknown">No lo sé</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-primary/60">
          Autopromoción
          <select value={form.allows_self_promo} onChange={(e) => update("allows_self_promo", e.target.value as Community["allows_self_promo"])} className="min-w-0 rounded-lg border border-primary/15 px-2 py-1.5 text-sm">
            <option value="yes">Sí</option>
            <option value="no">No</option>
            <option value="limited">Limitada</option>
            <option value="unknown">No lo sé</option>
          </select>
        </label>
      </div>

      <SectionDisclosure title="Notas y reglas">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            URL de las reglas
            <input value={form.rules_url} onChange={(e) => update("rules_url", e.target.value)} className="rounded-lg border border-primary/15 px-2.5 py-1.5 text-sm" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            Última revisión de las reglas
            <input type="date" value={form.rules_last_reviewed_at} onChange={(e) => update("rules_last_reviewed_at", e.target.value)} className="rounded-lg border border-primary/15 px-2.5 py-1.5 text-sm" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-primary/60">
            Notas
            <textarea value={form.notes} onChange={(e) => update("notes", e.target.value)} rows={2} className="rounded-lg border border-primary/15 p-2.5 text-sm" />
          </label>
        </div>
      </SectionDisclosure>

      {dirty && (
        <button
          onClick={() => save.mutate({})}
          className="mt-2 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-accent hover:bg-primary-hover"
        >
          Guardar cambios
        </button>
      )}
    </div>
  );
}

export default function Communities() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [newForm, setNewForm] = useState<CommunityForm>(EMPTY_FORM);

  const query = useQuery({ queryKey: ["communities"], queryFn: () => api.get<Community[]>("/api/communities") });

  const create = useMutation({
    mutationFn: () => api.post<Community>("/api/communities", newForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["communities"] });
      toast.show("Comunidad creada");
      setShowForm(false);
      setNewForm(EMPTY_FORM);
    },
  });

  return (
    <div>
      <PageHeader
        title="Comunidades"
        description="Subreddits vigilados, con sus reglas y prioridad. Añádelas manualmente."
        action={
          <button
            onClick={() => setShowForm((s) => !s)}
            className="flex min-h-[40px] items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-semibold text-accent hover:bg-primary-hover"
          >
            <Plus size={15} aria-hidden="true" />
            Añadir comunidad
          </button>
        }
      />

      {showForm && (
        <div className="mb-4 rounded-card border border-primary/10 bg-white p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs text-primary/60">
              Nombre (sin r/)
              <input
                value={newForm.name}
                onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))}
                className="rounded-lg border border-primary/15 px-2.5 py-2 text-sm"
                placeholder="agency"
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

      {query.isLoading && <LoadingState label="Cargando comunidades…" />}
      {query.isError && <ErrorState message="No se pudieron cargar las comunidades." onRetry={() => query.refetch()} />}
      {query.isSuccess && query.data.length === 0 && (
        <EmptyState title="Todavía no hay comunidades" description="Añade el primer subreddit que quieres vigilar." />
      )}
      {query.data && query.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {query.data.map((c) => (
            <CommunityCard key={c.id} community={c} />
          ))}
        </div>
      )}
    </div>
  );
}
