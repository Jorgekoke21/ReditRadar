# Arquitectura

## Stack

- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + React Router + TanStack Query + lucide-react.
- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + Alembic + Pydantic v2.
- **Base de datos**: PostgreSQL (Supabase en producciÃ³n, contenedor `postgres:16-alpine` en local).
- **Jobs programados**: proceso `worker` independiente (APScheduler), separado del proceso API.
- **Infraestructura objetivo**: Supabase (Postgres + Auth), frontend en Vercel, backend + worker en Render.
  Todo tambiÃ©n corre 100% en local vÃ­a Docker Compose.

## Por quÃ© estas decisiones

- **FastAPI async de punta a punta**: los jobs (anÃ¡lisis, purga, alertas) son I/O-bound (DB + HTTP opcional a un
  proveedor de IA); async evita bloquear el proceso API mientras corren.
- **Un worker separado en vez de jobs dentro del proceso API**: si el worker se cae o se reinicia, la API sigue
  respondiendo. TambiÃ©n es el proceso que en producciÃ³n se despliega como "Background Worker" en Render,
  independiente del "Web Service".
- **SQLAlchemy `Uuid` y `Enum(native_enum=False)`** en vez de tipos especÃ­ficos de Postgres: el modelo de datos es
  portable a SQLite, lo que permite que la suite de tests corra sin depender de un Postgres real (ver
  `docs/testing.md`). Postgres sigue siendo el motor real en dev/staging/producciÃ³n.
- **RLS con efecto real, verificado empÃ­ricamente**: el backend se conecta con roles (`radar_app`/`radar_worker`)
  que no son propietarios de las tablas y no tienen `BYPASSRLS` â€” a diferencia del rol `radarin`, que Alembic sigue
  usando solo para migraciones. El aislamiento entre cuentas ya no depende solo de que cada consulta filtre por
  `account_id`: aunque un filtro se olvidara en algÃºn endpoint, Postgres seguirÃ­a negando el acceso a filas fuera
  del `app.account_id` fijado en la transacciÃ³n. Ver `docs/rls.md` para el diseÃ±o completo y las pruebas
  reproducibles contra Postgres real (`backend/tests/test_rls_postgres.py`).
- **Analyzer como interfaz (`ConversationAnalyzer`)**: `RulesConversationAnalyzer` es la implementaciÃ³n por
  defecto y no tiene dependencias externas; `LLMConversationAnalyzer` solo se instancia si
  `AI_ANALYSIS_ENABLED=true` y hay `AI_API_KEY`. La app nunca deja de funcionar por falta de IA.
- **EmailProvider como interfaz**: `ConsoleEmailProvider` (por defecto) nunca "miente" diciendo que enviÃ³ un
  correo â€” el llamador siempre persiste un `AlertDelivery` para que el correo sea visible en `/alerts` aunque no
  haya salido de verdad. `SMTPEmailProvider` y `ResendEmailProvider` estÃ¡n implementados y listos para activarse
  con configuraciÃ³n real.
- **Adaptador de Reddit oficial y puerta de seguridad**: app/services/reddit_client.py usa OAuth bearer y solo
  endpoints de lectura. REDDIT_API_ENABLED=false corta antes de crear el cliente HTTP. Con la bandera activa,
  fetch_reddit_conversations usa comunidades activas, watermark persistente, dedupe y el pipeline existente.
  La integraciÃ³n real sigue sin estar probada/aprobada porque no hay credenciales autorizadas en este entorno.

## Ãrbol de archivos principal

```
radarin-conversation-radar/
â”œâ”€â”€ docker-compose.yml
â”œâ”€â”€ .env.example
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ main.py                 # FastAPI app + routers + CORS
â”‚   â”‚   â”œâ”€â”€ worker.py               # proceso APScheduler independiente
â”‚   â”‚   â”œâ”€â”€ config.py               # Settings (pydantic-settings)
â”‚   â”‚   â”œâ”€â”€ db.py                   # engine/session async + reaplicaciÃ³n de GUCs RLS por transacciÃ³n
â”‚   â”‚   â”œâ”€â”€ core/security.py        # auth: verificaciÃ³n real de JWT Supabase + AuthenticatedPrincipal + modo dev
â”‚   â”‚   â”œâ”€â”€ models/                 # SQLAlchemy ORM (19 tablas)
â”‚   â”‚   â”œâ”€â”€ schemas/                # Pydantic request/response
â”‚   â”‚   â”œâ”€â”€ api/                    # routers: health, auth, dashboard,
â”‚   â”‚   â”‚                           #   conversations, communities, topics,
â”‚   â”‚   â”‚                           #   alerts, jobs, settings, reddit, history
â”‚   â”‚   â”œâ”€â”€ services/
â”‚   â”‚   â”‚   â”œâ”€â”€ dedupe.py           # normalizaciÃ³n URL/tÃ­tulo + hash
â”‚   â”‚   â”‚   â”œâ”€â”€ scoring.py          # motor de puntuaciÃ³n 0-100
â”‚   â”‚   â”‚   â”œâ”€â”€ initial_filter.py   # filtro determinista (secciÃ³n 10)
â”‚   â”‚   â”‚   â”œâ”€â”€ analyzer.py         # ConversationAnalyzer + Rules/LLM
â”‚   â”‚   â”‚   â”œâ”€â”€ drafts.py           # generaciÃ³n de 3 variantes de borrador
â”‚   â”‚   â”‚   â”œâ”€â”€ email_provider.py   # Console/SMTP/Resend
â”‚   â”‚   â”‚   â”œâ”€â”€ email_templates.py  # HTML de digest/alerta/semanal
â”‚   â”‚   â”‚   â”œâ”€â”€ reddit_client.py    # adaptador OAuth oficial de solo lectura
â”‚   â”‚   â”‚   â”œâ”€â”€ crypto.py           # cifrado Fernet de tokens OAuth
â”‚   â”‚   â”‚   â””â”€â”€ jobs.py             # los 8 jobs + locking + bookkeeping + contexto RLS por cuenta
â”‚   â”‚   â””â”€â”€ seeds/demo_data.py      # 14 comunidades, 10 temas, 20 conversaciones
â”‚   â”œâ”€â”€ alembic/versions/           # 5 migraciones (schema, RLS, roles+RLS efectivo, profiles.email no-unique, ingesta Reddit/observabilidad)
â”‚   â””â”€â”€ tests/                      # 81 tests potenciales; 72 pasan con SQLite/FakeReddit y 9 se omiten sin Postgres
â””â”€â”€ frontend/
    â””â”€â”€ src/
        â”œâ”€â”€ pages/                  # Login, Today, Conversations, ConversationDetail,
        â”‚                           #   ManualImport, Communities, Topics, Alerts,
        â”‚                           #   History, Settings, Diagnostics
        â”œâ”€â”€ components/             # AppShell, Sidebar, MobileNavigation, PageHeader,
        â”‚                           #   ConversationRow, ScoreIndicator, PromotionRisk,
        â”‚                           #   RecommendedAction, EmptyState, LoadingState,
        â”‚                           #   ErrorState, FilterBar, MobileFilterSheet,
        â”‚                           #   ReplyEditor, OutcomeForm, ConfirmationToast,
        â”‚                           #   SectionDisclosure
        â””â”€â”€ lib/                    # api.ts, auth.tsx, toast.tsx, format.ts
```

## Decisiones de simplificaciÃ³n (documentadas, deliberadas)

El encargo lista 23 tablas "como mÃ­nimo". Se implementaron 19 cubriendo el mismo comportamiento; dos
simplificaciones deliberadas:

1. **`topic_keywords` y `topic_exclusions` sÃ­ existen como tablas propias** (no se colapsaron en JSON), pero los
   ejemplos positivos/negativos de un tema se guardan como columnas `JSON` en `topics` en vez de tablas propias â€”
   son datos de solo lectura/referencia para quien redacta el tema, no se consultan ni indexan individualmente.
2. **No existe tabla `reddit_connections` por separado del resto de ajustes de integraciÃ³n** â€” sÃ­ existe, pero el
   estado "modo actual / IA / correo" que pide la pantalla `/settings` se calcula al vuelo desde `Settings`
   (variables de entorno) en vez de duplicarlo en una tabla de configuraciÃ³n; es derivado, no una fuente de verdad.

Ninguna de las dos simplificaciones elimina funcionalidad pedida: todas las pantallas y filtros del encargo
funcionan tal cual estÃ¡n especificados.

## VerificaciÃ³n visual

El proyecto tiene una suite de tests E2E con Playwright Test (`frontend/tests/e2e/`, 37 tests) que corre contra el
stack real levantado con `docker compose up`, incluida una prueba (`full-flow-and-screenshots.spec.ts`) que genera
y persiste en `docs/screenshots/` las capturas requeridas en cuatro resoluciones, comprobando en cada una ausencia
de scroll horizontal y ausencia de errores de consola. Regenerarlas: `cd frontend && npx playwright test`. Detalle
completo en `docs/testing.md`.


## Worker y pipeline Reddit

El worker usa AsyncIOScheduler con funciones coroutine registradas directamente, max_instances=1, coalesce=True
y ocho jobs explÃ­citos. Cada ejecuciÃ³n abre una sesiÃ³n independiente, conserva el locking DB y registra estado,
duraciÃ³n, errores y mÃ©tricas en scheduled_job_runs.

El job Reddit no crea un pipeline paralelo: recupera publicaciones, normaliza sus campos, consulta el mismo dedupe,
ejecuta el filtro determinista y llama a _analyze_one, que reutiliza topics, anÃ¡lisis, scoring y drafts. Las alertas
se generan despuÃ©s por los jobs existentes. El adapter permite FakeRedditClient para pruebas sin red.

