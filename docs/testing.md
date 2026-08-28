# Tests

Last audited: 2026-08-27 (see `docs/acceptance-audit.md` for the full matrix). The backend result below is from the isolated SQLite/FakeReddit run; the full Docker stack and browser suite were not rerun in this phase because host port 5432 was occupied by another project.

## Backend (81 tests potenciales; ultima ejecucion local: 72 passed, 9 skipped)

```bash
cd backend
docker compose run --rm --no-deps backend pytest -q
```

Resultado de esta fase: **72 passed, 9 skipped, 0 failed**. Los 9 omitidos requieren el servicio Postgres/RLS y no se ejecutan en la invocacion aislada con `--no-deps`. Para ejecutar los checks de Postgres contra la base real de Compose: `docker compose run --rm backend pytest tests/test_rls_postgres.py -v`.

Corren contra un SQLite de archivo desechable (no contra el Postgres de desarrollo) — todos los modelos usan tipos
portables (`Uuid`, `Enum(native_enum=False)`, `JSON`) precisamente para que esto sea posible sin depender de un
Postgres real. Cada test recibe una base de datos limpia (`tests/conftest.py` hace `drop_all` + `create_all` antes
de cada test).

| Archivo | Qué verifica |
|---|---|
| `test_scoring.py` | La puntuación nunca sale de [0, 100], los componentes del desglose suman el total, los umbrales de clasificación (85/70/55/40) son exactos, la penalización por riesgo promocional se aplica. |
| `test_dedupe.py` | Normalización de URL y título, hash estable, e idempotencia real end-to-end vía la API (`POST /api/conversations/manual` dos veces con el mismo payload no duplica). |
| `test_retention.py` | `expires_at` se fija a 48h en la creación manual, `purge_expired_reddit_content` limpia `raw_*` pero conserva puntuación/resumen, es idempotente (segunda ejecución no hace nada), y el borrado manual inmediato funciona. |
| `test_ownership.py` | Una cuenta no puede leer, listar ni editar conversaciones o comunidades de otra cuenta — a nivel de aplicación. **No prueba RLS**: ver la nota sobre RLS más abajo y en `docs/acceptance-audit.md`. |
| `test_csv_import.py` | Parseo de CSV, fila inválida no aborta el resto, mensaje de error con el número de fila, reimportar el mismo archivo no duplica, y las filas importadas quedan analizadas de inmediato. |
| `test_alerts.py` | El límite diario de alertas urgentes se respeta aunque haya más candidatas, no se reenvía una alerta ya enviada el mismo día, el resumen diario no se envía sin destinatario configurado, y el **resumen semanal** genera una entrega real con estadísticas correctas (o no genera nada si está desactivado). |
| `test_jobs.py` | El bloqueo de jobs (`ScheduledJobRun` en estado `running`) hace que una segunda invocación se salte en vez de correr en paralelo; `fetch_reddit_conversations` y `sync_deleted_reddit_content` son no-op mientras `REDDIT_API_ENABLED=false`; `/api/reddit/connect` responde 403. |
| `test_initial_filter.py` | Detección de ofertas de empleo y spam/cripto, antigüedad máxima configurable, y descarte quieto cuando no hay coincidencia de tema. |
| `test_text_utils.py` | El emparejamiento de palabras clave es insensible a acentos ("página" encuentra "pagina"). |
| `test_analyzer_and_secrets.py` | `get_analyzer` siempre cae a reglas si la IA está desactivada o sin API key; el cifrado de tokens OAuth nunca deja el texto plano visible en el ciphertext; ninguna respuesta de la API (`/api/auth/dev-login`, `/api/settings/integrations`) incluye tokens ni secretos. |
| `test_auth_jwt.py` | Verificación real de JWT de Supabase (firmado con un proveedor JWT local, ver `docs/authentication.md`): firma incorrecta, expirado, `iss`/`aud` incorrectos, sin `sub`, malformado, sin token; aprovisionamiento en primer login (verificado contra la base de datos, no solo por la respuesta HTTP); idempotencia entre logins repetidos; dev-login y JWT con el mismo email nunca se fusionan en la misma cuenta; el backend ignora un `account_id` inyectado en el cuerpo de la petición. |
| `test_startup_guard.py` | El proceso se niega a arrancar con `APP_ENV=production` + `AUTH_MODE=development`, y con `AUTH_MODE=supabase` sin `SUPABASE_JWT_SECRET` — probado spawneando un subproceso real de Python (`subprocess.run([sys.executable, "-c", "import app.main"])`), no solo llamando a una función. |
| `test_rls_postgres.py` | RLS efectivo contra Postgres real: `radar_app`/`radar_worker` sin `BYPASSRLS`, no propietarios de las tablas; cero filas visibles sin `app.account_id`; aislamiento entre dos cuentas; una conexión nueva del pool no hereda el contexto de otra; dos contextos concurrentes no se cruzan; el grant extra de `radar_worker` para listar cuentas no se filtra a otras tablas. Ver `docs/rls.md` para el detalle fila por fila. |

**Nota sobre RLS**: a diferencia de una fase anterior de este proyecto (ver la sección histórica de
`docs/acceptance-audit.md`), RLS **sí tiene efecto real** hoy, verificado por `test_rls_postgres.py` contra
Postgres real, no por inferencia. Detalle completo del diseño de roles y políticas en `docs/rls.md`.

## Frontend E2E (37 tests, Playwright Test, contra el stack real)

```bash
cd frontend
npx playwright test
```

Ultima ejecucion completa registrada antes de esta fase: **35 passed**, 0 failed, 0 skipped.
Esta fase añade dos pruebas en reddit-automation.spec.ts; la ejecucion de los 37 tests quedo pendiente por el conflicto de puerto 5432.

| Archivo | Qué verifica |
|---|---|
| `login.spec.ts` | El formulario de login real (rellenar email, enviar) lleva a `/today`; una ruta protegida sin sesión redirige a `/login`. |
| `auth.spec.ts` | Solicitar un enlace mágico muestra la confirmación de "enviado" (llamada de red a Supabase interceptada, ya que no existe un proyecto Supabase real en este entorno); una sesión Supabase genuina y simulada (firmada localmente con el mismo secreto que el backend verifica, con la misma forma exacta que persiste `@supabase/supabase-js`) se recupera de `localStorage` y autentica sin llamada de red; una sesión con un JWT expirado (pero válidamente firmado) pierde el acceso; cerrar sesión limpia el estado y una ruta protegida vuelve a exigir login; el formulario de acceso de desarrollo no aparece en absoluto cuando el backend reporta `AUTH_MODE=supabase`; la página de callback muestra el error real que Supabase reporta en la URL para un enlace inválido/expirado. |
| `today.spec.ts` | Estado vacío accionable en una cuenta nueva; la bandeja lista una conversación real con puntuación/acción/máximo dos badges; "Revisar ahora" dispara de verdad las llamadas a `/api/jobs/analyze_pending_conversations/run` y `/recalculate_scores/run` (no es un botón decorativo). |
| `filters.spec.ts` | Buscar y filtrar por subreddit cambian de verdad el resultado (comprobado también a nivel de red, no solo visual); un filtro sin resultados muestra un estado vacío accionable. |
| `manual-import.spec.ts` | Validación en línea de campos obligatorios; el formulario crea una conversación real, analizada, con desglose de puntuación visible; la importación CSV reporta errores de fila sin descartar las filas válidas. |
| `conversation-detail.spec.ts` | La ficha muestra contenido real del análisis (no placeholders); el editor de borrador permite cambiar de variante, editar y el cambio persiste tras recargar; "Copiar respuesta" escribe de verdad en el portapapeles; "Abrir en Reddit" apunta a la URL real cuando existe, y **no se renderiza en absoluto** cuando la conversación no tiene URL (regresión del bug real encontrado en esta auditoría, ver más abajo); "Recalcular" y "Volver a analizar" disparan las llamadas reales al backend; "Eliminar contenido original ahora" purga de verdad. |
| `discard-undo.spec.ts` | Descartar cambia el estado en el servidor (comprobado vía API, no solo visualmente) y desaparece de la lista; "Deshacer" lo restaura, verificado también en el servidor; "Guardar" persiste el estado `saved`. |
| `mark-responded-history.spec.ts` | Marcar como respondida + registrar un resultado persiste tras recargar la página y aparece en `/history`; verificado también directamente contra la API. |
| `alerts.spec.ts` | La configuración de alertas persiste tras recargar (no es solo un toast); la bandeja de previsualización vacía muestra un estado accionable; el correo de prueba aparece marcado como NO enviado externamente (proveedor console); el resumen diario disparado desde `/diagnostics` genera un correo real visible en la bandeja. |
| `accessibility.spec.ts` | El foco de teclado es visible (outline real, no `none`) al tabular hasta el botón principal; el campo de email del login tiene un nombre accesible asociado. |
| `ownership.spec.ts` | Prueba de dos cuentas: la cuenta B no puede leer (404), listar, editar (404) ni registrar un resultado (404) sobre una conversación de la cuenta A, ni vía API ni navegando directamente a su URL en el navegador. |
| `reddit-automation.spec.ts` | Simulacion controlada de ingesta Reddit en Hoy, score/accion/borrador y ejecucion segura del job desactivado desde Diagnostico. |
| `full-flow-and-screenshots.spec.ts` | El flujo principal completo de punta a punta (login → importar → analizar → puntuación → borrador → editar → copiar → abrir en Reddit → marcar respondida → registrar resultado → verlo en historial → configurar alerta → previsualizar resumen diario), sin ningún error de consola, y genera las capturas requeridas en `docs/screenshots/`. |

### Bugs reales encontrados por estos tests (no simulados, corregidos en el mismo commit)

1. **Botón "Abrir en Reddit" muerto**: las conversaciones manuales sin URL guardaban una URI ficticia
   (`manual://subreddit/título`) como su `url`, y el botón enlazaba a esa URI no abrible. Corregido en
   `backend/app/api/conversations.py` (el identificador sintético ya solo se usa para deduplicar, nunca se expone
   como `url`) y en el frontend (el botón ahora no se renderiza cuando no hay URL real, en vez de enlazar a algo
   roto).
2. **HMR de Vite no funcionaba dentro de Docker en Windows**: el watcher de archivos nunca detectó ediciones hechas
   desde el host (0 líneas de recarga en los logs durante toda la sesión), así que el contenedor servía un bundle
   desactualizado tras cada cambio sin avisar. Corregido activando `usePolling` en `frontend/vite.config.ts`.
   Cualquier verificación visual hecha antes de este fix en este mismo proyecto debe considerarse sospechosa de
   estar mirando código viejo.
3. **`.dockerignore` ausente**: sin él, `docker compose build` copiaba el `node_modules` del host (compilado para
   Windows) encima del `node_modules` correctamente instalado dentro del contenedor Linux, arriesgando binarios
   nativos incompatibles (confirmado: `@rollup/rollup-linux-x64-musl` desaparecía). Corregido añadiendo
   `frontend/.dockerignore` y `backend/.dockerignore`.
4. **`run_send_weekly_digest` rompía en cuanto había un tema real que coincidiera** (`Topic.id == top_topic_id`
   comparando la columna UUID contra un `str`) — nunca se había detectado porque no existía ningún test que
   ejecutara ese job. Corregido en `backend/app/services/jobs.py` y cubierto ahora por
   `test_weekly_digest_persists_a_real_delivery_with_correct_stats`.
5. **Política RLS de `profiles` circular** (fase de autenticación real, 2026-07-27): comparaba
   `account_id = current_setting('app.account_id')`, pero no se puede conocer el `account_id` de un usuario sin
   antes leer su fila de `profiles` — que es justo lo que esa política pretendía proteger. Nunca se había
   detectado porque RLS no tenía efecto real hasta esta fase. Corregido con una política de autolectura por UUID
   propio (`docs/rls.md`).
6. **`profiles.email` con restricción `unique=True`** (fase de autenticación real, 2026-07-27): un login de
   desarrollo y un login JWT real con el mismo email lanzaban un `IntegrityError` (500 crudo) al intentar
   aprovisionar la segunda identidad, porque el email se trataba de facto como clave de identidad — contradice la
   instrucción explícita de usar solo el UUID de Supabase. Encontrado por
   `test_provisioning_never_merges_accounts_by_email`, corregido quitando la unicidad
   (`backend/alembic/versions/0004_profiles_email_not_unique.py`).
7. **GUC de RLS se reseteaba a `''` tras el primer `commit()`** (fase de autenticación real, 2026-07-27): Postgres
   resetea un GUC personalizado a cadena vacía (no `NULL`) en cuanto termina la transacción que lo fijó por primera
   vez con `SET LOCAL`, y además `AsyncSession` de SQLAlchemy puede devolver una conexión física distinta del pool
   tras cada `commit()` — un segundo intento de arreglo (GUC a nivel de sesión) tampoco bastaba porque ese `SET` no
   viaja entre conexiones físicas distintas. Se manifestaba como un `InvalidTextRepresentationError: invalid input
   syntax for type uuid: ""` al aprovisionar una cuenta nueva. Corregido con un listener de evento ORM `after_begin`
   que reaplica el contexto guardado en `session.info` a cualquier conexión que respalde una nueva transacción —
   ver "El bug sutil descubierto durante esta fase" en `docs/rls.md`.

## Frontend: type-checking

`npm run build` ejecuta `tsc --noEmit` antes de compilar — el build falla si hay un error de tipos. Verificado sin
errores tras cada cambio de UI.

## QA visual

Capturas reales verificadas y guardadas en [`docs/screenshots/`](screenshots/), generadas por
`full-flow-and-screenshots.spec.ts` contra el stack recién reconstruido (no capturas manuales sueltas):
`today-desktop-1440x900.png`, `today-desktop-1280x800.png`, `today-tablet-768x1024.png`,
`today-mobile-390x844.png`, `conversation-desktop.png`, `conversation-mobile.png`, `manual-import.png`,
`alerts.png`. El mismo test comprueba en cada resolución que no hay scroll horizontal
(`document.documentElement.scrollWidth <= clientWidth`) y que no hay errores de consola en toda la sesión.

## Flujo principal (sección 22 del encargo) — automatizado, no solo probado a mano

1. Entrar (`/login`, formulario real).
2. Importar conversación manual (`/manual-import`).
3. Se analiza automáticamente al crearla.
4. Ver puntuación con desglose (`/conversations/:id`, sección "Desglose de puntuación").
5. Generar/ver borrador de respuesta (`ReplyEditor`, variantes educativa / suave / directa).
6. Editar el borrador (persiste tras recargar).
7. Copiar borrador (clipboard real, confirmación por toast).
8. Abrir en Reddit (enlace real verificado).
9. Marcar como respondida (persiste en servidor).
10. Registrar resultado (`OutcomeForm`, persiste en servidor).
11. Verla en Historial (`/history`).
12. Configurar una alerta (persiste tras recargar).
13. Previsualizar el resumen diario (generado de verdad vía el job, visible en la bandeja).

Cubierto por `full-flow-and-screenshots.spec.ts`, ejecutable en cualquier momento con `npx playwright test`.


## Tests de automatización Reddit y worker

tests/test_reddit_ingestion.py usa FakeRedditClient y cubre:

- flag desactivada con cero llamadas;
- credenciales OAuth ausentes con fallo seguro;
- fetch de comunidad activa, pipeline real, dedupe y watermark persistente;
- sync de contenido eliminado;
- contenido antiguo/eliminado descartado antes del analyzer;
- 429/500/timeouts con retry-after y backoff limitado;
- puerta administrativa de jobs y diagnostics.
- scheduler real ejecutando automáticamente el job dos veces, registrando scheduled_job_runs y continuando
  después de un resultado fallido.

Los tests no sustituyen la aprobación ni una prueba contra Reddit real. Para una ejecución local sin Docker se deben
instalar las dependencias de backend/requirements.txt; la suite existente también contiene tests PostgreSQL que se
omiten si db no está disponible.
