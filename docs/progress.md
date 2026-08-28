# Bitácora de progreso

Proyecto construido en una sesión continua (2026-07-27). Registro por fase, tal como pide el encargo.

## Fase 0 — Requisitos y arquitectura

- Revisados los 29 apartados del encargo, arquitectura definida en `docs/architecture.md`.
- Decisión: SQLAlchemy con tipos portables (`Uuid`, `Enum(native_enum=False)`) para poder testear sin depender de
  un Postgres real, manteniendo Postgres como motor real en dev/staging/prod.
- Riesgo identificado y resuelto pronto: Python 3.14 (versión instalada en el host) no tiene wheels precompilados
  para `pydantic-core`/`asyncpg`/`greenlet` en Windows y no hay toolchain de compilación (`link.exe`/MSVC)
  disponible → se descartó el venv local y se movió todo el desarrollo/ejecución del backend a Docker
  (`python:3.12-slim`), donde sí hay wheels. Documentado para que quien retome el proyecto no repita el intento.

## Fase 1 — Backend, base de datos, Demo

- `docker-compose.yml` (db + backend + worker + frontend), `.env.example`.
- 19 tablas modeladas, dos migraciones de Alembic generadas por autogenerate contra Postgres real
  (`27e66f7e965c_initial_schema.py`, `0002_row_level_security.py` escrita a mano para las políticas RLS).
- Auth: `core/security.py` con verificación de JWT de Supabase (HS256) + modo `dev_auth_bypass` para poder usar la
  app entera sin credenciales de Supabase.
- Seed de demo: 14 comunidades, 1 perfil de vigilancia, 10 temas con palabras clave/exclusiones, 20 conversaciones
  ficticias cubriendo los escenarios pedidos (agencia buscando clientes, diseñador sin clientes, Google Maps, CRM,
  SEO local, oferta de empleo, promoción de curso, meme, alto riesgo promocional, español e inglés).
- **Bug real encontrado y corregido durante el seed**: el emparejamiento de palabras clave usaba `.lower()` simple
  y fallaba con variantes acentuadas ("página" no encontraba "pagina") y con conjugaciones — se añadió
  `app/services/text_utils.normalize` (fold de acentos) usado de forma consistente en `analyzer.py`,
  `initial_filter.py`, `jobs.py` y `dedupe.py`. Antes del fix, 14/20 conversaciones de demo se descartaban por
  error; después, la distribución de puntuaciones es realista y cubre todos los escenarios pedidos.
- Migraciones aplicadas y datos sembrados **desde cero** dos veces durante la sesión (una vez antes del fix de
  acentos, otra después, con `docker compose down -v` de por medio) para verificar que el arranque en frío
  funciona de verdad, no solo la primera vez.

## Fase 2 y 3 — Frontend, importación manual, scoring, análisis, borradores

- Motor de reglas (`RulesConversationAnalyzer`), filtro inicial determinista (`initial_filter.py`), motor de
  puntuación explicable (`scoring.py`) y generador de 3 variantes de borrador (`drafts.py`) implementados sin
  ninguna dependencia externa.
- **Segundo bug real encontrado con los tests (no con pruebas manuales)**: `jobs.py` asignaba
  `convo.topic_id = result.topic_ids[0]` como *string* a una columna tipada `Uuid`. Postgres lo toleraba de forma
  implícita (por eso no se detectó probando manualmente contra el stack Docker), pero SQLite lo rechazaba en seco
  — al escribir la suite de tests contra SQLite, saltó inmediatamente. Corregido con `uuid.UUID(...)`. Se dejó
  como nota: SQLite fue más estricto que Postgres aquí y eso ayudó a encontrar un bug real de tipado.
- **Tercer bug real**: el filtro inicial exigía que el subreddit estuviera registrado como comunidad activa
  incluso para conversaciones manuales — rompía el requisito explícito de que el modo Manual funcione "sin
  ninguna API externa" y sin configuración previa. Corregido para que ese chequeo solo aplique a
  `source_mode=reddit_api` (ver `docs/manual-mode.md`).
- Frontend completo: 11 pantallas, 17 componentes reutilizables, sistema visual con los tokens de marca de
  Radarin (`#062F25` / `#0A4638` / `#A3FF12` / `#F1F8F5`), Tailwind, responsive verificado en 4 resoluciones.

## Fase 4 — Emails, jobs, retención, auditoría, diagnóstico

- `EmailProvider` (Console/SMTP/Resend), plantillas HTML de digest diario/alerta urgente/resumen semanal.
- 8 jobs implementados con locking basado en `ScheduledJobRun` (una segunda invocación mientras hay una en curso
  se salta, no corre en paralelo) y pantalla `/diagnostics` para dispararlos manualmente y ver su histórico.
- `purge_expired_reddit_content` verificado end-to-end contra Postgres real: se forzó `expires_at` al pasado con
  SQL directo, se ejecutó el job vía API, y se confirmó que `raw_title`/`raw_body` quedan en `NULL` mientras
  `score_total` y `summary` sobreviven.

## Fase 5 — Adaptador de Reddit (desactivado)

- `reddit_client.py` implementa el flujo OAuth completo de solo lectura, pero cada función pública comprueba
  `REDDIT_API_ENABLED` y lanza `RedditIntegrationDisabled` si está apagado — no hay ningún camino de código que
  llegue a `oauth.reddit.com` mientras la bandera esté en `false` (valor por defecto).
- `docs/reddit-compliance.md` y `docs/reddit-access-request.md` documentan exactamente qué falta para activarlo.

## Fase 6 — Tests, QA visual, documentación

- 40 tests de backend, todos en verde, corridos dentro de Docker contra SQLite (ver `docs/testing.md` para el
  porqué de esa elección).
- QA visual con Playwright headless contra el stack Docker completo (frontend + backend + db + worker
  levantados con `docker compose up`), 4 resoluciones, **cero errores de consola** en las 11 pantallas. Se
  encontraron y corrigieron 3 defectos visuales menores durante esa revisión: el subreddit se mostraba en
  mayúsculas por un `uppercase` en el contenedor equivocado (r/SaaS → R/SAAS), la insignia "Riesgo bajo/medio"
  se partía en dos líneas, y los `<select>` de Comunidades truncaban el texto de las opciones más largas.
- Esta documentación.

## Fase 7 — Auditoría de aceptación (2026-07-27, sesión separada)

Auditoría completa pedida explícitamente sin confiar en el informe de la Fase 6. Reconstrucción desde cero
(`docker compose down -v && up --build`) repetida 3 veces durante esta fase. Resultado completo con evidencia
reproducible en **`docs/acceptance-audit.md`** — ese archivo es ahora la fuente de verdad sobre qué está completo,
parcial, simulado o pendiente, y sustituye cualquier afirmación optimista de fases anteriores en caso de conflicto.

Hallazgos y correcciones de esta fase:

1. **Bug real: botón "Abrir en Reddit" muerto.** Las conversaciones manuales sin URL guardaban una URI ficticia
   (`manual://subreddit/título`) como su `url` pública, y el botón enlazaba ahí. Corregido en
   `backend/app/api/conversations.py` (el identificador sintético ahora solo se usa para deduplicar) y en el
   frontend (el botón no se renderiza si no hay URL real). Test de regresión añadido.
2. **Bug de infraestructura: HMR de Vite no funcionaba dentro de Docker en Windows.** El watcher de archivos nunca
   detectó ediciones hechas desde el host (0 líneas de recarga en los logs desde el arranque del contenedor), así
   que el contenedor servía un bundle desactualizado tras cada cambio, sin avisar. Esto invalida cualquier
   verificación visual hecha en la Fase 6 después del primer cambio de frontend en esa sesión. Corregido activando
   `usePolling` en `frontend/vite.config.ts`.
3. **Bug de build: `.dockerignore` ausente.** `docker compose build` copiaba el `node_modules` del host (Windows)
   encima del `node_modules` instalado dentro del contenedor Linux — riesgo real de binarios nativos
   incompatibles, confirmado con `@rollup/rollup-linux-x64-musl`. Corregido añadiendo `frontend/.dockerignore` y
   `backend/.dockerignore`.
4. **Bug real: `send_weekly_digest` crasheaba con temas reales.** `Topic.id == top_topic_id` comparaba la columna
   UUID contra un `str`. Nunca se había detectado porque ningún test ejecutaba ese job (cobertura 0% antes de esta
   auditoría). Corregido en `backend/app/services/jobs.py`, cubierto ahora por un test dedicado.
5. **Afirmación corregida: RLS no protege nada hoy.** La Fase 1 activó RLS en Postgres y la documentación lo
   describía como "defensa en profundidad". Verificado empíricamente que el rol de base de datos del backend
   (`radarin`, propietario de las tablas) queda exento de RLS por defecto en Postgres — una consulta con
   `app.account_id` puesto a un UUID inexistente sigue devolviendo todas las filas de todas las cuentas. Los
   documentos (`data-model.md`, `architecture.md`, `README.md`) se corrigieron para no dar a entender que RLS
   aporta protección alguna en el estado actual; el aislamiento real es 100% código de aplicación, ya verificado
   con pruebas de dos cuentas.
6. **Afirmación corregida: la integración de Reddit "implementada" no significa "funcional al activarla".** Se
   descubrió que `fetch_reddit_conversations` y `sync_deleted_reddit_content` son stubs que no hacen nada incluso
   con `REDDIT_API_ENABLED=true` y credenciales válidas — nunca llaman a `fetch_new_posts`. `docs/reddit-compliance.md`
   ahora tiene una tabla de clasificación por capacidad en vez de una afirmación global de "implementado".
7. **Afirmación corregida: el docstring de `reddit_client.py` decía que se respetaban las cabeceras
   `x-ratelimit-*`.** Falso — solo se lee `retry-after` en respuestas de error. Corregido en el código y en la
   documentación.
8. Suite de tests de frontend añadida de verdad: 29 tests con Playwright Test (`frontend/tests/e2e/`), contra el
   stack real, no contra mocks — cubre bandeja Hoy, filtros, importación, ficha, copiar, marcar respondida,
   descartar/deshacer, alertas, estados vacíos, ownership de dos cuentas, accesibilidad (foco/label), y el flujo
   principal completo con generación de capturas reales en `docs/screenshots/`.
9. Tests de backend ampliados de 40 a 42 (cobertura nueva del resumen semanal).

## Estado final

Ver `docs/acceptance-audit.md` para el resumen ejecutivo con evidencia verificable (qué es completo, parcial,
simulado, bloqueado por credenciales o no implementado). Este archivo es el registro histórico de cómo se
construyó y auditó el proyecto; para el estado del código, la fuente de verdad es el propio código, `git log`, y
`docs/acceptance-audit.md`.

## Fase 4 — Autenticación real con Supabase y aislamiento real mediante RLS (2026-07-27, sesión posterior)

Cierra los dos huecos que la auditoría de la Fase 3 documentó explícitamente: login simulado (no Supabase Auth
real) y RLS sin efecto práctico (el rol del backend era propietario de las tablas). Alcance explícitamente excluido
por el encargo de esta fase: recogida automática de Reddit, publicación en Reddit, IA real, pantallas nuevas.

- **Auditoría previa del repo real** (no del informe anterior): confirmado con `\du` que `radarin` es superusuario
  con `BYPASSRLS`, y con una consulta SQL directa que `SET app.account_id` a un UUID inexistente seguía devolviendo
  todas las filas — el mismo hallazgo que la auditoría original, verificado de nuevo desde cero.
- **Roles separados**: migración `0003_app_role_and_rls_hardening.py` crea `radar_app` y `radar_worker`
  (`NOSUPERUSER NOBYPASSRLS`, no propietarios), con grants explícitos y `ALTER DEFAULT PRIVILEGES`. `radarin` queda
  reservado exclusivamente para Alembic (`DATABASE_MIGRATION_URL`).
- **Política de `profiles` corregida**: era circular (`account_id = current_setting('app.account_id')` sin poder
  conocer aún el `account_id`); ahora es autolectura por `id = current_setting('app.user_id')`.
- **`FORCE ROW LEVEL SECURITY`** en las 19 tablas con datos de cuenta, como defensa en profundidad adicional.
- **Backend**: `AuthenticatedPrincipal`, verificación real de JWT de Supabase (firma HS256, `iss`, `aud`, `exp`,
  `sub`), `AUTH_MODE=supabase|development` con guardias de arranque (`app/main.py` se niega a arrancar si
  `APP_ENV=production` + `AUTH_MODE=development`, o si `AUTH_MODE=supabase` sin `SUPABASE_JWT_SECRET`),
  aprovisionamiento idempotente por UUID (nunca por email).
- **Bug sutil encontrado y corregido**: Postgres resetea un GUC personalizado a `''` tras el primer `commit()` de
  la transacción que lo fijó, y `AsyncSession` puede además cambiar de conexión física del pool en cada
  `commit()` — un simple `SET LOCAL` o incluso un `SET` de sesión no bastaba. Corregido con un listener de evento
  ORM `after_begin` que reaplica el contexto guardado en `session.info` a cualquier conexión que respalde una
  nueva transacción (`backend/app/db.py`). Ver `docs/rls.md` para el detalle completo.
- **`profiles.email` dejó de ser único** (migración `0004_profiles_email_not_unique.py`) — tenía `unique=True`,
  lo que fusionaba de facto la identidad por email y contradecía la instrucción explícita de usar solo el UUID de
  Supabase; encontrado por un test que provisionaba la misma dirección desde dos identidades distintas.
- **Frontend**: `@supabase/supabase-js` real (magic link, persistencia de sesión, recuperación al cargar, logout,
  `/auth/callback`), estados de UI para enviando/enviado/sesión expirada/token inválido/error de configuración, y
  el formulario de desarrollo oculto por completo (no solo deshabilitado) cuando `AUTH_MODE=supabase`.
- **Entorno local**: se usó un proveedor JWT local (mismo contrato de verificación exacto que un JWT real de
  Supabase, sin servidor real) para los tests automatizados, más el modo desarrollo explícito para el navegador
  interactivo — nunca presentado como si fuera Supabase real. No existe un proyecto Supabase real en este entorno.
- **Tests**: backend de 42 a 69 (27 nuevos: JWT válido/rechazado en 8 variantes + aprovisionamiento, guardias de
  arranque vía subproceso real, spoof de `account_id` ignorado, y 10 tests de RLS directo contra Postgres real —
  privilegios de rol, propiedad de tablas, aislamiento con y sin contexto, no fuga de contexto entre conexiones del
  pool, concurrencia real, grant acotado del worker). Frontend E2E de 29 a 35 (6 nuevos: magic link, sesión
  Supabase simulada recuperada de `localStorage`, expiración de sesión, logout, ocultación del login de desarrollo
  en modo Supabase, error de enlace inválido).
- **Documentación nueva**: `docs/authentication.md`, `docs/rls.md`. Actualizados: `README.md`,
  `docs/architecture.md`, `docs/data-model.md`, `docs/deployment.md`, `docs/testing.md`,
  `docs/acceptance-audit.md` (§4 sustituida, histórico conservado sin editar al final del documento).

## Siguiente tarea exacta si se retoma el proyecto

En orden de valor (ver también `docs/deployment.md` y `docs/acceptance-audit.md`):

1. Ejecutar el login real contra un proyecto Supabase real (hoy probado solo con un proveedor JWT local — ver
   `docs/authentication.md` para la clasificación explícita de qué está probado contra qué) y añadir las Redirect
   URLs del dominio de producción en Supabase Auth antes de desplegar.
2. Escribir la lógica real de `fetch_reddit_conversations` (reunir comunidades vigiladas → token de la cuenta →
   `fetch_new_posts` por comunidad → persistir vía el mismo pipeline que la importación manual) y de
   `sync_deleted_reddit_content` — hoy son stubs aunque se active la bandera.
3. Solicitar acceso a la Data API de Reddit (`docs/reddit-access-request.md`) y, una vez aprobado, completar el
   punto 2 antes de activar `REDDIT_API_ENABLED`.
4. Añadir un test que fuerce un fallo real dentro de un job para verificar que `ScheduledJobRun.error_message` se
   rellena correctamente (hoy solo verificado por lectura de código).


## Fase de automatización (2026-08-27)

Implementado en código, sin conexión real a Reddit:

- worker asyncio/APScheduler con ocho jobs directos, lifecycle limpio, locking e informes persistentes;
- fetch oficial con comunidades activas, watermark por comunidad, filtro antes del analyzer, dedupe y métricas;
- backoff limitado con jitter para 429/5xx/timeouts y captura de headers x-ratelimit-*;
- sync de eliminados vía /api/info, solo ante marcador explícito;
- guardia contra clave de cifrado vacía/fallback al activar Reddit;
- endpoint de jobs con puerta administrativa explícita y diagnóstico de integración;
- demo idempotente que relativiza únicamente filas is_demo;
- tests FakeRedditClient y scheduler real sin llamadas de red.
- VerificaciÃ³n cerrada: 72 passed, 9 skipped en backend; la suite E2E queda en 37 tests y no se ejecutÃ³ por el conflicto de puerto 5432.

No está activado ni aprobado Reddit real. Faltan la aprobación, credenciales OAuth, redirect URI de producción, clave
de cifrado de producción y una verificación final contra el entorno autorizado.
