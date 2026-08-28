# Auditoría de aceptación — Radar de Conversaciones

**Fecha de la auditoría original**: 2026-07-27. **Fecha de la fase de autenticación real (Supabase Auth + RLS
efectivo)**: 2026-07-27, misma fecha, sesión posterior.

**§4 de este documento (Autenticación y ownership) queda sustituida por completo** por el resultado de la fase de
autenticación real — ver la sección "§4 — Autenticación y ownership (actualizado)" más abajo. El contenido
histórico original de esa sección se conserva al final del documento, sin editar, como registro de auditoría (qué
se encontró y cuándo), no como estado actual del código.

**Método (ambas fases)**: reconstrucción completa desde cero (`docker compose down -v && docker compose up --build`),
pruebas automatizadas ejecutadas contra el stack real (no contra mocks), inspección directa de Postgres vía `psql`
y consultas SQL directas contra los roles reales (`radar_app`/`radar_worker`, no `radarin`), y scripts de auditoría
ejecutados dentro del contenedor real. No se asumió nada de ningún informe anterior — cada fila de cada tabla tiene
un comando o archivo verificable al lado.

**Resultado global**: el MVP funciona de punta a punta en modo Demo y Manual, sin llamadas externas, sin romperse
por falta de credenciales. La auditoría original encontró y corrigió **4 bugs reales** (no cosméticos): un botón
"Abrir en Reddit" muerto, HMR de Vite roto en Docker/Windows, ausencia de `.dockerignore`, y un crash en
`send_weekly_digest` nunca antes ejercitado por ningún test — y documentó que RLS no tenía efecto real. La fase de
autenticación real **corrigió ese hallazgo de RLS** (ahora protege de verdad, verificado empíricamente) y encontró
**3 bugs reales adicionales** durante su propio desarrollo: una política RLS circular en `profiles`, una
restricción de unicidad en `profiles.email` que contradecía la instrucción de usar solo el UUID de Supabase como
identidad, y un bug sutil de Postgres/SQLAlchemy que reseteaba el contexto de RLS tras el primer `commit()` de cada
sesión (ver `docs/testing.md` para el detalle de los tres).

---

## §4 — Autenticación y ownership (actualizado, fase de autenticación real, 2026-07-27)

| Requisito | Estado real | Evidencia | Archivo o endpoint | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|---|
| Login real con Supabase Auth (magic link) | **Completo**, probado con un proveedor JWT local | `@supabase/supabase-js` real (`signInWithOtp`, `getSession`, `onAuthStateChange`, `signOut`); backend verifica firma/`iss`/`aud`/`exp`/`sub` de verdad | `frontend/src/lib/auth.tsx`, `supabaseClient.ts`, `backend/app/core/security.py::verify_supabase_jwt` | `test_auth_jwt.py` (12), `auth.spec.ts` (6) | **No probado contra un proyecto Supabase real** (no existe uno en este entorno) — probado contra un proveedor JWT local que mina tokens con el contrato exacto que el backend verifica, y contra una sesión simulada con la forma exacta que `@supabase/supabase-js` persiste | Ejecutar contra un proyecto Supabase real antes de desplegar a producción |
| Verificación real de JWT (firma, `iss`, `aud`, `exp`, `sub`) | Completo | Cada comprobación tiene un test que la fuerza a fallar y confirma 401 | `backend/app/core/security.py::verify_supabase_jwt` | `test_auth_jwt.py` (7 tests de rechazo + 1 camino feliz) | Probado con proveedor JWT local, no con Supabase real | Ver arriba |
| `account_id` nunca viene del cliente | Completo | Un `account_id` inyectado en el cuerpo de `POST /api/conversations/manual` se ignora; la fila creada pertenece a la cuenta del token | `backend/app/core/security.py` (todos los routers usan `get_current_account_id`) | `test_backend_ignores_client_supplied_account_id` | Ninguna | Ninguna |
| Aprovisionamiento idempotente, sin usar email como identidad | Completo | Logins repetidos con el mismo `sub` resuelven a la misma cuenta; dev-login y JWT con el mismo email crean cuentas **distintas** | `backend/app/core/security.py::_resolve_profile` | `test_provisioning_is_idempotent_across_repeated_logins`, `test_provisioning_never_merges_accounts_by_email` | Ninguna | Ninguna |
| Modo desarrollo separado, nunca en producción | Completo | El proceso se niega a arrancar con `APP_ENV=production` + `AUTH_MODE=development`, o con `AUTH_MODE=supabase` sin `SUPABASE_JWT_SECRET` — probado spawneando un subproceso real | `backend/app/main.py` | `test_startup_guard.py` (4 tests, subprocess real) | Ninguna | Ninguna |
| El login de desarrollo no aparece en modo Supabase | Completo | El formulario ni siquiera está en el DOM cuando `config.auth_mode !== "development"` | `frontend/src/pages/Login.tsx` | `auth.spec.ts::dev login is not offered when the backend reports AUTH_MODE=supabase` | Ninguna | Ninguna |
| RLS protege de verdad (no solo declarado) | **Completo** — corrige el hallazgo de la auditoría original | El rol del backend (`radar_app`/`radar_worker`) no es propietario de las tablas y no tiene `BYPASSRLS`; verificado con consultas directas a catálogo de Postgres | `backend/alembic/versions/0003_app_role_and_rls_hardening.py`, `docs/rls.md` | `test_rls_postgres.py` (10 tests contra Postgres real) | Ninguna | Ninguna |
| Aislamiento entre cuentas a nivel de base de datos (no solo de aplicación) | Completo | `radar_app` sin `app.account_id` ve 0 filas; con el de la cuenta A, no ve las de B — probado con SQL directo, no por inferencia | Ver arriba | `test_radar_app_sees_zero_rows_without_any_account_context`, `test_radar_app_with_account_a_context_cannot_see_account_b` | Ninguna | Ninguna |
| El pool de conexiones no filtra contexto entre peticiones | Completo | Una conexión nueva del pool no hereda el `app.account_id` fijado en otra; dos contextos concurrentes reales (`asyncio.gather`) nunca se cruzan | `backend/app/db.py` (listener `after_begin`) | `test_a_fresh_connection_never_inherits_a_previous_connections_account_context`, `test_two_concurrent_connections_keep_independent_account_context` | Ninguna | Ninguna |
| El worker itera por cuenta sin desactivar RLS | Completo | `radar_worker` tiene un grant adicional muy acotado (solo listar `accounts.id`), que no se filtra a ninguna otra tabla | `backend/app/services/jobs.py::_set_account_context` | `test_radar_worker_can_enumerate_accounts_but_still_needs_context_for_conversations`, `test_radar_app_cannot_list_accounts_it_does_not_own` | Ninguna | Ninguna |
| Roles separados: migraciones vs. app vs. worker | Completo | Alembic usa `DATABASE_MIGRATION_URL` (`radarin`); el backend usa `DATABASE_APP_URL` (`radar_app`); el worker usa `DATABASE_WORKER_URL` (`radar_worker`) — nunca se solapan | `backend/alembic/env.py`, `docker-compose.yml` | `test_migration_role_url_differs_from_app_role_url`, `test_radar_app_role_does_not_own_the_tables` | Ninguna | Ninguna |

**Clasificación explícita de pruebas (instrucción del encargo: no declarar Supabase Auth completo sin aclarar
contra qué se probó)**:

- **Probado con Supabase real**: ninguna prueba de esta fase — no existe un proyecto Supabase real disponible en
  este entorno.
- **Probado con un proveedor JWT local**: toda la verificación de JWT (`test_auth_jwt.py`, 12 tests) — mina tokens
  HS256 con el contrato exacto que `verify_supabase_jwt` comprueba, firmados con el mismo secreto que el backend
  usa, ejercitando el código real de verificación, sin servidor Supabase real involucrado.
- **Probado con una sesión Supabase simulada controlada**: `auth.spec.ts::a genuine (locally-signed) Supabase
  session recovered from storage logs the user in` — siembra en `localStorage` una sesión con la forma exacta que
  `@supabase/supabase-js` persiste tras un login real (mismo formato de clave `sb-<ref>-auth-token`, mismos campos),
  firmada con el mismo secreto local.
- **Probado solo mediante mocks (red interceptada)**: `auth.spec.ts::requesting a magic link shows the sent
  confirmation` intercepta la llamada HTTP a `auth/v1/otp` (no existe servidor real que responder) — prueba la UI
  de confirmación, no la entrega real del correo.
- **No probado**: el envío real de un correo de magic link por Supabase, y el flujo completo de clic en el enlace
  del correo real. Requiere un proyecto Supabase real.

Ver `docs/rls.md` y `docs/authentication.md` para el diseño completo, con evidencia y comandos reproducibles.

---

## Contenido histórico (auditoría original, 2026-07-27 — §4 más abajo superada, ver arriba)

## 1. Arranque desde cero

| Requisito | Estado real | Evidencia | Archivo o endpoint | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|---|
| Arranca con un solo comando documentado | Completo | `docker compose down -v` (borra volumen) → `docker compose up --build` → backend aplica migraciones y siembra datos automáticamente, ver logs | `docker-compose.yml`, `backend/Dockerfile` | Reconstrucción completa 3 veces durante esta auditoría, la última con los 4 bugs ya corregidos | Ninguna | Ninguna |
| Migraciones desde base de datos vacía | Completo | Logs: `Running upgrade -> 27e66f7e965c, initial schema` → `27e66f7e965c -> 0002_rls` sobre un volumen recién creado | `backend/alembic/versions/*.py` | Ejecutado en cada uno de los 3 rebuilds | Ninguna | Ninguna |
| Carga de datos iniciales (Demo) | Completo | Log: `Seeded demo account <uuid> with 20 conversations`; confirmado vía `GET /api/conversations` | `backend/app/seeds/demo_data.py` | Verificado tras cada rebuild | Ninguna | Ninguna |
| `.dockerignore` presente (evita copiar `node_modules`/`.venv` del host) | Completo (bug real corregido en esta auditoría) | Antes: ausente, `docker run --rm <img> sh -c "ls node_modules/@rollup"` no mostraba el binario Linux. Después: `@rollup/rollup-linux-x64-musl` presente en la imagen | `frontend/.dockerignore`, `backend/.dockerignore` | `docker run --rm radarin-conversation-radar-frontend sh -c "..."` | Ninguna | Ninguna |

## 2. Flujo principal

| Requisito | Estado real | Evidencia | Archivo o endpoint | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|---|
| Acceso (login) | Completo (pero ver §6 — no es Supabase Auth real) | Formulario real rellenado y enviado, llega a `/today` | `frontend/src/pages/Login.tsx` | `login.spec.ts` (2 tests) | Es un login de desarrollo, no un magic link real | Ver §6 |
| Bandeja Hoy | Completo | Lista conversaciones reales con puntuación, acción, máx. 2 badges | `frontend/src/pages/Today.tsx` | `today.spec.ts` (3 tests) | Ninguna | Ninguna |
| Apertura de una conversación | Completo | Navega a la ficha, muestra datos reales del análisis | `frontend/src/pages/ConversationDetail.tsx` | `conversation-detail.spec.ts` | Ninguna | Ninguna |
| Importación manual | Completo | Formulario crea conversación real vía `POST /api/conversations/manual`, redirige a su ficha | `frontend/src/pages/ManualImport.tsx` | `manual-import.spec.ts` (3 tests) | Ninguna | Ninguna |
| Análisis | Completo | Se ejecuta de forma síncrona al crear/importar; `RulesConversationAnalyzer` produce resultado real | `backend/app/services/jobs.py::_analyze_one` | Todos los tests de importación + `audit_no_network.py` | Ninguna | Ninguna |
| Puntuación y desglose | Completo | Desglose de 7 componentes + penalización, visible y verificado que suma el total | `backend/app/services/scoring.py` | `test_scoring.py` (6 tests) + `conversation-detail.spec.ts` | Ninguna | Ninguna |
| Generación de borradores | Completo | Hasta 3 variantes generadas al analizar (si la puntuación lo justifica) | `backend/app/services/drafts.py` | `conversation-detail.spec.ts` | Ninguna | Ninguna |
| Edición del borrador | Completo | Editar el textarea + recargar página conserva el cambio (verificado, no solo visual) | `frontend/src/components/ReplyEditor.tsx` | `conversation-detail.spec.ts::draft editor...persists on reload` | Ninguna | Ninguna |
| Copia | Completo | `navigator.clipboard.readText()` tras pulsar el botón devuelve exactamente el texto del borrador | `ReplyEditor.tsx` | `conversation-detail.spec.ts::copiar respuesta...` | Ninguna | Ninguna |
| Apertura de Reddit | Completo (bug real encontrado y corregido) | Antes: enlazaba a `manual://subreddit/título` (URI no abrible) cuando no había URL. Ahora: el botón no se renderiza si no hay URL real; enlaza a la URL real cuando existe | `backend/app/api/conversations.py`, `ConversationRow.tsx`, `ConversationDetail.tsx` | `conversation-detail.spec.ts` (2 tests, caso con y sin URL) | Ninguna | Ninguna |
| Marcar como respondida | Completo | Estado `responded` persiste en Postgres, verificado por recarga + consulta API directa | `POST /api/conversations/{id}/actions?action_type=marked_responded` | `mark-responded-history.spec.ts` | Ninguna | Ninguna |
| Registrar resultado | Completo | `POST /api/conversations/{id}/outcome` persiste `result`, `upvotes`, etc.; verificado vía API tras la acción de UI | `OutcomeForm.tsx` | `mark-responded-history.spec.ts` | Ninguna | Ninguna |
| Ver resultado en Historial | Completo | La conversación respondida aparece en `/history` tras recargar | `frontend/src/pages/History.tsx` | `mark-responded-history.spec.ts` | Ninguna | Ninguna |
| Configurar una alerta | Completo | Configuración persiste tras recargar la página (no solo un toast) | `frontend/src/pages/Alerts.tsx` | `alerts.spec.ts::alert settings persist across reload` | Ninguna | Ninguna |
| Previsualizar el resumen diario | Completo | Disparado vía `/diagnostics`, aparece en la bandeja de `/alerts` con `sent: false` | `AlertDelivery`, `email_provider.py` | `alerts.spec.ts::daily digest preview...` | Ninguna | Ninguna |
| Sin botones inertes | Completo tras corrección | Se encontró y corrigió el único botón muerto detectado ("Abrir en Reddit" sin URL) | — | Recorrido completo por Playwright de las 11 pantallas + inspección de cada botón con acción asociada | No se garantiza que sea exhaustivo al 100% — ver "Limitaciones generales" al final | Ninguna identificada |

## 3. Modos de funcionamiento

| Requisito | Estado real | Evidencia | Archivo o endpoint | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|---|
| Demo funciona sin llamadas externas | Completo | Pipeline de análisis real ejecutado con **todas** las conexiones de socket a IPs no privadas bloqueadas a nivel de `socket.socket.connect`; completó con éxito (`score_total=98`) | `backend/audit_no_network.py` | `docker compose exec backend python audit_no_network.py` | Prueba a nivel de socket, no de paquete de red completo (no hay captura pcap) | Ninguna |
| Manual funciona sin llamadas externas | Completo | Mismo script, mismo pipeline (`_analyze_one`), usado por manual/CSV | `backend/audit_no_network.py` | Igual que arriba | Igual que arriba | Ninguna |
| `REDDIT_API_ENABLED=false` impide cualquier llamada a Reddit | Completo; los jobs que lo usan están implementados y también respetan la bandera (ver §5) | Las 3 funciones públicas de `reddit_client.py` invocadas directamente y las 3 lanzan `RedditIntegrationDisabled` antes de tocar la red | `backend/app/services/reddit_client.py` | Invocación directa vía `docker compose exec` + `test_jobs.py` (2 tests) | Ninguna | Ninguna |
| `AI_ANALYSIS_ENABLED=false` usa realmente el analizador por reglas | Completo | `get_analyzer()` devuelve `RulesConversationAnalyzer` por defecto y también cuando está activado sin API key; con clave real, devuelve `LLMConversationAnalyzer` que **sí intenta una llamada HTTP real** (confirmado: `401 Unauthorized` de `api.openai.com`, prueba de que no es un stub) | `backend/app/services/analyzer.py` | Script interactivo de 3 escenarios, ver comando en el informe final | Ninguna | Ninguna |
| `EMAIL_PROVIDER=console` no declara correos como enviados | Completo | `ConsoleEmailProvider.send()` devuelve `False` siempre; verificado en vivo y en `alerts.spec.ts` | `backend/app/services/email_provider.py` | Invocación directa + `alerts.spec.ts::send-test email...NOT externally sent` | Ninguna | Ninguna |
| Falta de credenciales no rompe el programa | Completo | `.env` real del proyecto tiene `SUPABASE_*`, `REDDIT_CLIENT_*`, `AI_API_KEY`, `SMTP_HOST`, `RESEND_API_KEY` todos vacíos; `/api/health` y `/api/settings/integrations` responden con normalidad; 42+29 tests pasan bajo esta misma configuración | `.env`, `/api/settings/integrations` | `curl` en vivo + toda la suite de tests | Ninguna | Ninguna |

## 4. Autenticación y ownership (histórico — ver "§4 — Autenticación y ownership (actualizado)" al principio del documento para el estado real actual)

| Requisito | Estado real | Evidencia | Archivo o endpoint | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|---|
| Sistema de login que funciona hoy | **Simulado** (no es Supabase Auth) | `POST /api/auth/dev-login` crea/recupera un perfil a partir de un email sin ninguna verificación (ni email real, ni contraseña, ni enlace mágico); emite un token opaco `dev:<uuid>` | `backend/app/api/auth.py`, `backend/app/core/security.py` | `login.spec.ts` prueba el flujo, no prueba autenticidad porque no la hay | Cualquiera que conozca o adivine un email puede crear/recuperar esa sesión; no hay contraseña ni posesión de la bandeja de entrada verificada | Integrar `@supabase/supabase-js` (documentado en `docs/deployment.md`) |
| Parte de Supabase Auth implementada | Parcial | Existe código que verifica un JWT HS256 real de Supabase (`jwt.decode(..., algorithms=["HS256"], audience="authenticated")`) y mapea `sub`→`profiles.id` | `backend/app/core/security.py:75-89` | **Cero tests lo ejercitan** (`grep -rn "supabase_jwt_secret\|jwt.decode" backend/tests` → sin resultados) | Nunca se ha ejecutado contra un JWT real de un proyecto Supabase — no hay proyecto Supabase configurado en este entorno | Configurar un proyecto Supabase de prueba y añadir un test que genere un JWT válido y lo verifique |
| Parte simulada | Simulado | El botón "Continuar" del login real llama a `dev-login`, no a `supabase.auth.signInWithOtp` | `frontend/src/lib/auth.tsx` | — | El texto bajo el formulario de login ya lo advierte ("Este entorno funciona en modo desarrollo... En producción este mismo formulario envía un enlace mágico de Supabase Auth") | Ver deployment.md |
| Cómo se obtiene `account_id` | Completo | `get_current_account_id` → `profile.account_id`, `profile` resuelto desde el token (dev o JWT real), nunca desde un parámetro de la petición | `backend/app/core/security.py:92-93` | Usado por los 11 routers de la API | Ninguna | Ninguna |
| Cómo se evita el acceso entre cuentas | Completo (a nivel de aplicación) | Cada query de cada router filtra explícitamente por `account_id` | Todos los archivos en `backend/app/api/` | `test_ownership.py` (3 tests) + `ownership.spec.ts` (2 tests, navegador real, dos cuentas) | Ninguna a nivel de aplicación | Ninguna |
| ¿Las políticas RLS se ejecutan realmente en PostgreSQL? | **Parcial / Engañoso si no se aclara**: existen y están activas (`relrowsecurity=true`), pero **no tienen ningún efecto** contra el único rol que usa el backend | Prueba SQL directa (ver abajo) | `backend/alembic/versions/0002_row_level_security.py` | `docker compose exec db psql ...` (comando exacto abajo) | El rol `radarin` es propietario de las tablas → Postgres lo exime de RLS por defecto (`relforcerowsecurity=false`) | Si se quiere RLS real: crear un rol no-propietario, `GRANT` explícito, `ALTER TABLE ... FORCE ROW LEVEL SECURITY`, y hacer que el backend se conecte con ese rol en vez de con el propietario |
| ¿El usuario de base de datos del backend puede eludir RLS? | **Sí, siempre, hoy** | Ver prueba reproducible abajo | — | — | — | — |

### Prueba reproducible: RLS no protege al rol del backend

```bash
docker compose exec db psql -U radarin -d radarin_radar -c "
SET app.account_id = '00000000-0000-0000-0000-000000000000';  -- UUID que no existe en accounts
SELECT count(*) FROM conversations;"
```

Resultado obtenido: **66** (todas las conversaciones de todas las cuentas de la base de datos en ese momento, no
`0`). Confirmado también:

```sql
SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='conversations';
--  relrowsecurity | relforcerowsecurity
-- ----------------+---------------------
--  t              | f
SELECT current_user, (SELECT rolname FROM pg_roles WHERE oid=(SELECT relowner FROM pg_class WHERE relname='conversations'));
--  current_user | table_owner
-- --------------+-------------
--  radarin      | radarin
```

### Prueba reproducible: dos cuentas, aislamiento real (a nivel de aplicación)

```bash
cd frontend && npx playwright test tests/e2e/ownership.spec.ts
```

Resultado: 2/2 passed. La cuenta B recibe `404` al leer (`GET`), no aparece en el listado (`GET` lista), recibe
`404` al intentar modificar (`PATCH`) o registrar un resultado (`POST .../outcome`) sobre una conversación de la
cuenta A — verificado tanto por llamadas directas a la API como navegando a la URL de la ficha en un navegador
real con la sesión de la cuenta B.

## 5. Adaptador de Reddit

Ver tabla de clasificación completa en `docs/reddit-compliance.md` (sección "Clasificación por capacidad"). Resumen:

| Capacidad | Estado real |
|---|---|
| Puerta de activación (`RedditIntegrationDisabled` en las 3 funciones públicas) | Implementada y probada |
| `build_authorize_url` | Implementada, no probada contra Reddit real |
| `exchange_code_for_token` | Implementada, no probada contra Reddit real |
| `fetch_new_posts` / `fetch_new_posts_page` (listing + paginación + backoff) | Implementada y probada con Fake, no probada contra Reddit real |
| Job `fetch_reddit_conversations` | Implementado y probado con Fake, no probado contra Reddit real — **ya no es un stub** (corregido en la fase de automatización del 2026-08-27; esta fila decía "Stub" y era obsoleta) |
| Job `sync_deleted_reddit_content` | Implementado y probado con Fake, no probado contra Reddit real — **ya no es un stub** (misma corrección) |
| `refresh_access_token` + refresco proactivo antes de cada job | Implementado y probado con Fake, no probado contra Reddit real (fase puente OAuth) |
| Callback OAuth alcanzable desde el navegador (`/reddit/callback` en el frontend → `POST /api/reddit/callback` autenticado) | Implementado y probado con Fake/E2E, no probado contra Reddit real |
| `state` OAuth ligado a la cuenta, con expiración y un solo uso | Implementado y probado |
| Botón Conectar/Desconectar Reddit en Configuración | Implementado y probado con E2E |
| Cifrado de tokens OAuth (`crypto.py`) | Implementada y probada (`test_token_encryption_roundtrip_never_stores_plaintext`) |
| Backoff ante 429/5xx | Implementada, no probada contra Reddit real |
| Respetar cabeceras `x-ratelimit-*` | Implementada: se leen y persisten por comunidad (`reddit_rate_*`) y se exponen en diagnósticos; el backoff reacciona a 429/5xx/`retry-after`. No probada contra Reddit real |
| Scopes de solo lectura | Implementada |
| `GET /api/reddit/connect` bloqueado si desactivado | Implementada y probada (403 confirmado) |

No se realizó ninguna llamada real a Reddit durante esta auditoría, ni se activó la integración, ni se usó scraping.

## 6. Alertas y jobs

| Requisito | Estado real | Evidencia | Prueba ejecutada | Limitación | Acción pendiente |
|---|---|---|---|---|---|
| Resumen diario | Completo | Genera `AlertDelivery` real con `sent=false`; verificado en Postgres, no solo por HTTP 200 | `test_alerts.py` (2 tests) + `alerts.spec.ts` | Ninguna | Ninguna |
| Alerta urgente | Completo | — | `test_alerts.py::test_urgent_alerts_respect_daily_cap_and_avoid_duplicates` | Ninguna | Ninguna |
| Límite máximo diario | Completo | 3 conversaciones cualifican, solo 2 generan entrega (tope=2) | Mismo test | Ninguna | Ninguna |
| No duplicación | Completo | Segunda ejecución el mismo día: `processed=0` | Mismo test | Ninguna | Ninguna |
| Resumen semanal | Completo **tras corregir un bug real** (`Topic.id == top_topic_id` comparaba UUID contra `str`, crasheaba en cuanto había un tema con coincidencias) | `AlertDelivery` real verificado en Postgres tras disparar el job en vivo | `test_alerts.py::test_weekly_digest_persists_a_real_delivery_with_correct_stats` (nuevo) + disparo en vivo vía `curl` | Nunca se había probado antes de esta auditoría (0% cobertura) | Ninguna, ya corregido y cubierto |
| Purga a las 48 horas | Completo | `expires_at` forzado al pasado directamente en Postgres, job disparado vía API real, `raw_title` queda `NULL` y `score_total`/`summary` sobreviven — verificado con `SELECT` directo, no solo por la respuesta HTTP | `test_retention.py` (4 tests) + prueba en vivo (comando en el informe final) | Ninguna | Ninguna |
| Locking de tareas | Completo | Fila `running` insertada directamente en Postgres → segunda invocación vía API real responde `{"skipped": true, "reason": "already_running"}` | `test_jobs.py::test_job_lock_skips_when_already_running` + prueba en vivo | Ninguna | Ninguna |
| Idempotencia | Completo | Purga ejecutada dos veces: la segunda procesa 0 filas | `test_retention.py::test_purge_job_is_idempotent_noop_on_second_run` | Ninguna | Ninguna |
| Registro de errores | Completo | `ScheduledJobRun.error_message`/`error_count` se rellenan si `fn()` lanza una excepción | `backend/app/services/jobs.py::_with_job_lock` | No hay un test que fuerce una excepción real dentro de un job para verificar el registro — cubierto solo por lectura de código | Añadir un test que inyecte un fallo controlado |

## 7. Tests

Cifras de la auditoría original (histórico):

| Suite | Comando | Nº tests | Superados | Fallidos | Omitidos | Duración |
|---|---|---|---|---|---|---|
| Backend | `docker compose run --rm -e DATABASE_URL=sqlite+aiosqlite:///./test_radar.db backend pytest -q` | 42 | 42 | 0 | 0 | 25.64s |
| Frontend E2E | `cd frontend && npx playwright test` | 29 | 29 | 0 | 0 | ~60s |

**Cifras actuales tras la fase de autenticación real (2026-07-27, misma fecha, sesión posterior)**:

| Suite | Comando | Nº tests | Superados | Fallidos | Omitidos | Duración |
|---|---|---|---|---|---|---|
| Backend | `docker compose run --rm -e DATABASE_URL=sqlite+aiosqlite:///./test_radar.db backend pytest -q` | 69 | 69 | 0 | 0 | ~43s |
| Frontend E2E | `cd frontend && npx playwright test` | 35 | 35 | 0 | 0 | ~66s |

Ambas suites se ejecutaron contra el stack reconstruido desde cero. Ningún test se sustituyó por una comprobación
manual — cada afirmación de comportamiento de frontend en esta tabla tiene un `.spec.ts` correspondiente en
`frontend/tests/e2e/`. Ver `docs/testing.md` para el desglose archivo por archivo de los 27 tests nuevos (12 de
`test_auth_jwt.py`, 4 de `test_startup_guard.py`, 10 de `test_rls_postgres.py`, 1 de spoof de `account_id`, y 6 de
`auth.spec.ts`).

## 8. QA visual

Capturas reales guardadas en [`docs/screenshots/`](screenshots/): `today-desktop-1440x900.png`,
`today-desktop-1280x800.png`, `today-tablet-768x1024.png`, `today-mobile-390x844.png`, `conversation-desktop.png`,
`conversation-mobile.png`, `manual-import.png`, `alerts.png`. Generadas por
`full-flow-and-screenshots.spec.ts`, no capturadas a mano.

| Comprobación | Resultado |
|---|---|
| Sin scroll horizontal | Verificado automáticamente en las 8 capturas (`scrollWidth <= clientWidth`) |
| Sin textos cortados | Inspección visual de las 8 capturas — sin cortes |
| Sin botones fuera de pantalla | Inspección visual — todos los botones dentro del viewport en las 4 resoluciones |
| Máximo dos badges por conversación | Verificado visualmente (una insignia de riesgo + el nombre del tema en texto plano, no insignia) y por diseño del componente `ConversationRow.tsx` |
| Acción principal evidente | "Revisar ahora" en Hoy, "Marcar como respondida"/"Copiar respuesta" en la ficha, con color de acento diferenciado |
| Densidad compacta | Filas de conversación de una altura moderada, sin tarjetas gigantes |
| Focus visible | `accessibility.spec.ts::keyboard focus is visible...` — outline real verificado por CSS computado, no solo visual |
| Contraste suficiente | **No verificado con herramienta automatizada** (no se ejecutó axe-core ni Lighthouse en esta auditoría) — el sistema de color fue diseñado con AA en mente pero esto es una afirmación de diseño, no una medición |
| Consola sin errores | Verificado en las 29 pruebas E2E (`page.on('console'/'pageerror')`) — cero errores acumulados en toda la sesión de `full-flow-and-screenshots.spec.ts` |

## Limitaciones generales de esta auditoría

- No se ejecutó ninguna herramienta automatizada de contraste de color (axe-core/Lighthouse) — la accesibilidad de
  color es una afirmación de diseño, no medida.
- La prueba de "sin llamadas externas" opera a nivel de `socket.socket.connect`, que cubre `httpx`, `asyncpg` y
  cualquier librería estándar de Python — no es una captura de paquetes a nivel de red, pero es la comprobación
  más rigurosa practicable sin herramientas adicionales.
- No se han probado los endpoints de Reddit OAuth (`exchange_code_for_token`, `fetch_new_posts`) contra la Reddit
  real, porque el encargo de esta auditoría prohíbe explícitamente activar la integración o llamar a Reddit.
- El registro de errores de jobs (`ScheduledJobRun.error_message`) se verificó por lectura de código, no con un
  test que fuerce un fallo real.
- "Sin botones inertes" se verificó recorriendo las 11 pantallas y las rutas de prueba E2E, no mediante un
  escáner automatizado de cada elemento clicable de la aplicación — no puede garantizarse el 100% de cobertura.


---

## Fase siguiente: automatización (2026-08-27)

### Estado del worker

- Antes: jobs registrados con lambda -> asyncio.create_task, sin lifecycle del task, sin prueba de ejecución
  programada y con riesgo de RuntimeError: no running event loop.
- Después: AsyncIOScheduler recibe ocho coroutines directas; cada job tiene trigger, max_instances=1, coalescing y
  cierre controlado. _with_job_lock conserva el lock DB y persiste duración, estado, errores y métricas.
  tests/test_reddit_ingestion.py::test_scheduler_runs_job_automatically_and_survives_failed_callback deja ejecutar
  el job dos veces mediante trigger real y confirma dos filas scheduled_job_runs.

### Estado Reddit

| Capacidad | Estado |
|---|---|
| OAuth | Preparado, simulado en tests; bloqueado por aprobación/credenciales |
| Fetch oficial | Implementado, simulado con FakeRedditClient; no probado contra Reddit real |
| Rate limits, backoff y retry limitado | Implementado y probado con 429/500/timeout; cuota real no validada |
| Watermark/cursor | Completo en base de datos por comunidad; probado ante segunda ejecución |
| Ingesta/pipeline | Completo sobre servicios existentes; no hay pipeline paralelo |
| Dedupe | Completo por post id, URL normalizada y hash |
| Deleted sync | Parcial: solo marcadores explícitos de /api/info; ausencias no se consideran borrado |
| Jobs | Ocho registrados y cubiertos; worker real depende del entorno Docker |
| Alertas | Pipeline existente conectado; urgente excluye respondidas/descartadas/expiradas; ConsoleEmailProvider sigue en preview |
| Activación real | Bloqueada por aprobación, OAuth y clave de cifrado de producción |

### Activación real pendiente

1. Obtener aprobación oficial de Reddit.
2. Crear/configurar OAuth client id/secret y redirect URI autorizado.
3. Generar REDDIT_TOKEN_ENCRYPTION_KEY fuerte, no vacío y distinto del fallback.
4. Mantener REDDIT_API_ENABLED=false hasta completar lo anterior; luego ejecutar migraciones, callback y prueba
   controlada con límites.
5. Configurar JOB_ADMIN_EMAILS en producción.

### Verificación de esta fase

Ejecución disponible: backend base 60 passed, 9 skipped; tests de ingesta 11 passed y autorización 1 passed; total actual SQLite/FakeReddit
72 passed y 9 omitidos antes de los tests PostgreSQL opcionales. La suite E2E ahora contiene 37 tests; el reinicio completo y su ejecuciÃ³n no se pudieron certificar en
este entorno porque Docker tenÃ­a el puerto 5432 ocupado por otro proyecto.
Se aÃ±adiÃ³ la spec E2E de automatizaciÃ³n (2 tests); no se hizo push ni se llamÃ³ a Reddit real.
