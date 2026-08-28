import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Upload } from "lucide-react";
import { FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import { ApiError, api } from "../lib/api";
import { useToast } from "../lib/toast";
import type { ConversationListItem, CSVImportResult } from "../types";

export default function ManualImport() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [url, setUrl] = useState("");
  const [subreddit, setSubreddit] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [numComments, setNumComments] = useState("0");
  const [language, setLanguage] = useState("es");
  const [publishedAt, setPublishedAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [csvResult, setCsvResult] = useState<CSVImportResult | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!subreddit.trim()) next.subreddit = "Indica el subreddit.";
    if (!title.trim()) next.title = "Indica el título de la publicación.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    try {
      const convo = await api.post<ConversationListItem>("/api/conversations/manual", {
        url,
        subreddit: subreddit.replace(/^r\//, ""),
        title,
        body,
        num_comments: Number(numComments) || 0,
        language,
        published_at: publishedAt ? new Date(publishedAt).toISOString() : null,
      });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.show("Conversación importada y analizada");
      navigate(`/conversations/${convo.id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "No se pudo importar la conversación");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCsvChange() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setCsvUploading(true);
    setCsvResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api.postForm<CSVImportResult>("/api/conversations/import", form);
      setCsvResult(result);
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      toast.show(
        result.errors.length ? `Importación con avisos: ${result.imported} nuevas` : `${result.imported} conversaciones importadas`
      );
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "No se pudo procesar el CSV");
    } finally {
      setCsvUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div>
      <PageHeader
        title="Importar conversación"
        description="Funciona sin ninguna API externa: pega los datos de una publicación de Reddit o importa un CSV."
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <form onSubmit={handleSubmit} className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-3 text-sm font-semibold text-primary">Pegar una conversación</h2>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs text-primary/60">
              URL de Reddit (opcional)
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://reddit.com/r/agency/comments/..."
                className="min-h-[44px] rounded-lg border border-primary/15 px-3 text-sm text-primary placeholder:text-primary/35"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs text-primary/60">
              Subreddit
              <input
                value={subreddit}
                onChange={(e) => setSubreddit(e.target.value)}
                placeholder="agency"
                className={`min-h-[44px] rounded-lg border px-3 text-sm text-primary placeholder:text-primary/35 ${
                  errors.subreddit ? "border-red-400" : "border-primary/15"
                }`}
              />
              {errors.subreddit && <span className="text-red-600">{errors.subreddit}</span>}
            </label>

            <label className="flex flex-col gap-1 text-xs text-primary/60">
              Título
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className={`min-h-[44px] rounded-lg border px-3 text-sm text-primary ${
                  errors.title ? "border-red-400" : "border-primary/15"
                }`}
              />
              {errors.title && <span className="text-red-600">{errors.title}</span>}
            </label>

            <label className="flex flex-col gap-1 text-xs text-primary/60">
              Texto de la publicación
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={5}
                className="rounded-lg border border-primary/15 p-3 text-sm text-primary"
              />
            </label>

            <div className="grid grid-cols-3 gap-3">
              <label className="flex flex-col gap-1 text-xs text-primary/60">
                Comentarios
                <input
                  type="number"
                  min={0}
                  value={numComments}
                  onChange={(e) => setNumComments(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-primary/15 px-3 text-sm text-primary"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-primary/60">
                Idioma
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-primary/15 px-2 text-sm text-primary"
                >
                  <option value="es">Español</option>
                  <option value="en">English</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-primary/60">
                Fecha aprox.
                <input
                  type="date"
                  value={publishedAt}
                  onChange={(e) => setPublishedAt(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-primary/15 px-2 text-sm text-primary"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="mt-1 min-h-[44px] rounded-lg bg-primary text-sm font-semibold text-accent hover:bg-primary-hover disabled:opacity-60"
            >
              {submitting ? "Analizando…" : "Analizar e incorporar a la bandeja"}
            </button>
          </div>
        </form>

        <div className="rounded-card border border-primary/10 bg-white p-4 sm:p-5">
          <h2 className="mb-1 text-sm font-semibold text-primary">Importar CSV</h2>
          <p className="mb-3 text-sm text-primary/60">
            Columnas esperadas: url, subreddit, title, body, num_comments, language, published_at.
          </p>
          <label className="flex min-h-[120px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-primary/25 text-center text-sm text-primary/60 hover:border-primary/40">
            <Upload size={20} aria-hidden="true" />
            {csvUploading ? "Procesando…" : "Selecciona un archivo .csv"}
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleCsvChange} disabled={csvUploading} />
          </label>

          {csvResult && (
            <div className="mt-4 rounded-lg bg-surface p-3 text-sm">
              <p className="flex items-center gap-1.5 font-medium text-primary">
                <CheckCircle2 size={15} className="text-primary" aria-hidden="true" />
                {csvResult.imported} importadas · {csvResult.duplicates} ya existían
              </p>
              {csvResult.errors.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-red-600">
                  {csvResult.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
