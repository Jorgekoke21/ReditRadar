# Row Level Security (RLS)

**Estado a 2026-07-27**: RLS protege de verdad hoy — verificado empíricamente contra Postgres real (no solo por
diseño), en `backend/tests/test_rls_postgres.py` (10 tests). Esto sustituye por completo el hallazgo de la
auditoría previa (`docs/acceptance-audit.md`, sección histórica), que documentó — con la misma clase de prueba
directa — que RLS **no tenía ningún efecto** porque el backend se conectaba con el rol propietario de las tablas.

## El problema original (por qué RLS no protegía nada antes de esta fase)

Postgres exime del control de RLS a:

1. Superusuarios (`rolsuper = true`), siempre, sin excepción posible.
2. El propietario de la tabla (`relowner`), salvo que la tabla tenga `FORCE ROW LEVEL SECURITY`.

El único rol que existía (`radarin`) era ambas cosas: superusuario del contenedor Postgres de desarrollo, y
propietario de todas las tablas (las creó él mismo vía Alembic). Las políticas estaban declaradas y activas
(`relrowsecurity = true`), pero un `SET app.account_id` a un UUID inexistente seguido de
`SELECT count(*) FROM conversations` devolvía **todas** las filas de **todas** las cuentas — prueba reproducible
documentada en la auditoría previa.

## El diseño de esta fase: tres roles con responsabilidades distintas

| Rol | Usado por | Privilegios | ¿Propietario de tablas? | ¿BYPASSRLS? |
|---|---|---|---|---|
| `radarin` | Únicamente Alembic (`DATABASE_MIGRATION_URL`) | Superusuario del contenedor de desarrollo (en producción real sería un rol propietario normal, sin superusuario) | Sí | Sí (heredado de ser superusuario) |
| `radar_app` | El proceso API/backend (`DATABASE_APP_URL`), en cada petición | `CONNECT`, `USAGE` en `public`, `SELECT/INSERT/UPDATE/DELETE` en las tablas de la app, `USAGE/SELECT` en secuencias | **No** | **No** (`NOSUPERUSER NOBYPASSRLS` explícitos en `CREATE ROLE`) |
| `radar_worker` | El proceso `worker` (`DATABASE_WORKER_URL`), en cada job programado | Los mismos privilegios base que `radar_app`, **más** una política adicional muy acotada (ver abajo) | **No** | **No** |

El backend **nunca** se conecta como `radarin` para servir peticiones — solo Alembic lo usa, y solo para aplicar
migraciones (`backend/alembic/env.py` fuerza `settings.resolved_migration_url()`). Verificado explícitamente:
`test_migration_role_url_differs_from_app_role_url`, `test_radar_app_role_does_not_own_the_tables`,
`test_radar_app_role_has_no_bypassrls`, `test_radar_worker_role_has_no_bypassrls`.

`radar_app`/`radar_worker` se crean en la migración `0003_app_role_and_rls_hardening.py` con:

```sql
CREATE ROLE radar_app WITH LOGIN PASSWORD '<...>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION;
```

y reciben privilegios explícitos, nunca la propiedad de las tablas:

```sql
GRANT CONNECT ON DATABASE radarin_radar TO radar_app;
GRANT USAGE ON SCHEMA public TO radar_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO radar_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO radar_app;
ALTER DEFAULT PRIVILEGES FOR ROLE radarin IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO radar_app;
```

(La cláusula `ALTER DEFAULT PRIVILEGES` es la que garantiza que una tabla nueva creada por una migración futura
quede automáticamente accesible para `radar_app`/`radar_worker` sin tener que acordarse de un `GRANT` extra.)

## `FORCE ROW LEVEL SECURITY`

Aplicado a las 19 tablas con datos de cuenta:

```sql
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
```

Esto es defensa en profundidad: como `radar_app`/`radar_worker` **no** son propietarios, `FORCE` no cambia su
comportamiento (ya estaban sujetos a las políticas). Lo que sí garantiza es que si en el futuro alguien, por error,
conecta el backend con un rol que *sí* resulta ser propietario de las tablas, las políticas se siguen aplicando de
todas formas — la única forma de saltárselas seguiría siendo un superusuario real. `radarin` sigue siendo
superusuario en este docker-compose de desarrollo local precisamente para que Alembic pueda hacer DDL sin fricción;
en un despliegue real contra Supabase, el rol de migraciones sería propietario pero no superusuario, y `FORCE`
protegería incluso ese caso.

## Clasificación de las 19 tablas

| Categoría | Tablas | Política |
|---|---|---|
| Propiedad directa de cuenta | `accounts`, `communities`, `watch_profiles`, `topics`, `conversations`, `conversation_actions`, `alert_settings`, `alert_deliveries`, `reddit_connections`, `audit_logs` | `account_id = current_setting('app.account_id', true)::uuid` (o `id = ...` para `accounts` mismo) |
| Propiedad heredada vía FK (`EXISTS`) | `conversation_analysis`, `conversation_scores`, `reply_drafts`, `conversation_outcomes` (→ `conversations`); `topic_keywords`, `topic_exclusions` (→ `topics`); `watch_profile_communities` (→ `watch_profiles`) | `EXISTS (SELECT 1 FROM <padre> WHERE <padre>.id = <hija>.<fk> AND <padre>.account_id = current_setting(...))` |
| Caso especial: autolectura | `profiles` | `id = current_setting('app.user_id', true)::uuid` — ver "El bug circular de `profiles`" abajo |
| Sistema global | *(ninguna en este esquema — cada tabla cuelga de una cuenta o es solo de migraciones)* | — |

Las columnas usadas en cada `EXISTS`/comparación (`conversation_id`, `topic_id`, `watch_profile_id`, `account_id`)
ya tenían índice desde el esquema inicial (`index=True` en cada FK relevante en `backend/app/models/*.py`), así que
ningún índice nuevo hizo falta para que los `EXISTS` de las políticas sean baratos.

Cada política `FOR ALL` declara **tanto `USING` como `WITH CHECK`** explícitamente (antes eran implícitos, ver
`0003_app_role_and_rls_hardening.py`): `USING` filtra qué filas son visibles/editables/borrables, `WITH CHECK`
impide además que un `INSERT`/`UPDATE` deje una fila que apunte a una cuenta distinta de la del contexto activo —
sin `WITH CHECK`, sería posible seguir escribiendo filas fuera de la cuenta activa aunque no se pudieran leer
después.

## El bug circular de `profiles` (encontrado y corregido en esta fase)

La política original de `profiles` era `account_id = current_setting('app.account_id')` — pero no se puede conocer
el `account_id` de un usuario sin antes haber leído su fila de `profiles`, que es exactamente lo que esa misma
política pretendía proteger. Se corrigió con una política de autolectura basada en el UUID del propio usuario
(conocido de antemano, viene del `sub` del JWT ya verificado, antes de tocar la tabla):

```sql
CREATE POLICY self_lookup ON profiles
FOR ALL
USING (id = current_setting('app.user_id', true)::uuid)
WITH CHECK (id = current_setting('app.user_id', true)::uuid);
```

Por eso el backend mantiene **dos** GUCs por transacción, no solo uno: `app.user_id` (para poder resolver
`profiles` por sí mismo) y `app.account_id` (para todo lo demás, incluida la propia tabla `profiles` de forma
indirecta una vez resuelta).

## El grant adicional de `radar_worker`

Los jobs programados (`backend/app/services/jobs.py`) necesitan iterar "para cada cuenta, procesar sus
conversaciones pendientes" — es decir, necesitan poder listar **qué cuentas existen** antes de tener un
`app.account_id` fijado. Un rol que solo pudiera ver cuentas con el GUC ya puesto no podría arrancar ese bucle sin
desactivar RLS en algún punto, que es exactamente lo que el encargo prohíbe ("nunca desactivar RLS para jobs
globales"). La solución es una política adicional, mínima y explícita, solo para `radar_worker`:

```sql
CREATE POLICY worker_can_list_accounts ON accounts
FOR SELECT
TO radar_worker
USING (true);
```

Las políticas `PERMISSIVE` (el tipo por defecto en Postgres, y el único usado aquí) se combinan con `OR` — esta
política **añade** visibilidad de la lista de ids de `accounts` para `radar_worker` únicamente, y no afecta a
ninguna otra tabla ni a `radar_app`. Verificado explícitamente en ambas direcciones:

- `test_radar_worker_can_enumerate_accounts_but_still_needs_context_for_conversations`: `radar_worker` sin ningún
  `app.account_id` puede listar `accounts.id`, pero sigue viendo cero filas de `conversations` hasta que fija el
  contexto — el grant extra no se filtra a otras tablas.
- `test_radar_app_cannot_list_accounts_it_does_not_own`: `radar_app` (sin ese grant) obtiene una lista vacía al
  intentar lo mismo — confirma que el grant es específico de `radar_worker`, no una relajación global.

Cada iteración del bucle sigue fijando `app.account_id` antes de tocar cualquier tabla que no sea `accounts`
(`jobs.py::_set_account_context`, envoltorio de `remember_rls_context`) — RLS sigue activo en todo momento para
cualquier dato real de una cuenta.

## Cómo se fija el contexto por transacción (`SET LOCAL` / GUCs)

El backend fija dos GUCs por conexión antes de cualquier consulta que dependa de ellos:

```sql
SELECT set_config('app.user_id', '<uuid>', true);
SELECT set_config('app.account_id', '<uuid>', true);
```

El tercer argumento `true` es el equivalente funcional de `SET LOCAL`: el valor solo vive dentro de la transacción
actual y se descarta automáticamente al hacer `COMMIT` o `ROLLBACK` — nunca hay riesgo de que quede "pegado" a una
conexión física que luego el pool reutiliza para una petición de otra cuenta con un simple `SET` de sesión.

### El bug sutil descubierto durante esta fase (y por qué existe `app/db.py`'s `after_begin` listener)

Un primer intento ingenuo — fijar el GUC una vez al principio de la sesión con `is_local=true` — se rompía en
cuanto la sesión SQLAlchemy hacía su **segundo** `commit()`: Postgres resetea un GUC custom a `''` (cadena vacía,
**no** `NULL`) en cuanto termina la transacción que lo fijó por primera vez con `is_local=true`. Un segundo intento
— usar `is_local=false` (ámbito de sesión) — tampoco bastaba: `AsyncSession` de SQLAlchemy puede devolver la
conexión física al pool en cada `commit()` y, en el siguiente `autobegin`, tomar una conexión **distinta** del
pool — un `SET` a nivel de sesión en la conexión A simplemente no es visible en la conexión B.

La solución final (`backend/app/db.py`): un listener de evento ORM `after_begin` de SQLAlchemy, que se dispara en
**cada** inicio de transacción (incluidos los `autobegin` posteriores a un commit, en cualquier conexión física que
el pool decida entregar), y reaplica los valores guardados en `session.info` a la conexión que de verdad respalda
esa transacción:

```python
@event.listens_for(SyncSession, "after_begin")
def _reapply_rls_context_on_begin(session, transaction, connection):
    for guc_name, info_key in _INFO_KEYS.items():
        value = session.info.get(info_key)
        if value is not None:
            connection.execute(text("SELECT set_config(:name, :value, true)"), {"name": guc_name, "value": value})
```

`remember_rls_context(session, account_id=..., user_id=...)` es la única función que el resto del código llama; guarda
el valor deseado en `session.info` (que sobrevive a lo largo de la sesión) y lo aplica inmediatamente a la
conexión activa — el listener se encarga de que siga aplicado en cualquier transacción/conexión futura de esa misma
sesión, sin que el código de negocio tenga que pensar en pooling.

### Al terminar la sesión

`get_db()` (dependencia FastAPI) limpia el contexto en el `finally`, tanto de `session.info` como de la propia
conexión (`set_config('app.account_id', '', false)` explícito), antes de devolver la conexión al pool — para que
una conexión reutilizada por otra petición nunca arranque con un `app.account_id` residual de la petición anterior.

## Separación de URLs de conexión

| Variable | Usada por | Rol |
|---|---|---|
| `DATABASE_MIGRATION_URL` | Alembic (`alembic/env.py`) exclusivamente | `radarin` |
| `DATABASE_APP_URL` | El proceso API (`app/db.py`) | `radar_app` |
| `DATABASE_WORKER_URL` | El proceso worker (`app/worker.py`) | `radar_worker` |
| `DATABASE_URL` | Fallback de desarrollo/tests si las anteriores no están fijadas (p. ej. SQLite en la suite de tests) | — |

Verificado: `test_migration_role_url_differs_from_app_role_url` (las tres cadenas de conexión usan credenciales de
rol distintas, nunca la misma).

## Pruebas reproducibles

`backend/tests/test_rls_postgres.py` — deliberadamente **independiente** de `app.config`/`Settings` y de las
variables de entorno que la suite SQLite fuerza (`conftest.py`), porque estas pruebas verifican el comportamiento
del propio motor de base de datos, no el código de la aplicación por encima. Se conecta directamente a los tres
roles con sus credenciales locales de docker-compose. Ejecutar (contra el Postgres real, sin el override a SQLite):

```bash
docker compose run --rm backend pytest tests/test_rls_postgres.py -v
```

| Test | Qué prueba |
|---|---|
| `test_radar_app_role_has_no_bypassrls` / `test_radar_worker_role_has_no_bypassrls` | `pg_roles.rolbypassrls = false` para ambos roles — consulta directa a catálogo, no inferencia |
| `test_radar_app_role_does_not_own_the_tables` | `pg_get_userbyid(relowner)` de `conversations` es `radarin`, nunca `radar_app` |
| `test_migration_role_url_differs_from_app_role_url` | Las URLs de conexión usan roles distintos |
| `test_radar_app_sees_zero_rows_without_any_account_context` | `radar_app`, sin ningún `app.account_id` fijado, ve `0` filas de dos conversaciones reales sembradas por el rol de migraciones |
| `test_radar_app_with_account_a_context_cannot_see_account_b` | Con `app.account_id = A` fijado, solo la fila de la cuenta A es visible — la de B, no |
| `test_a_fresh_connection_never_inherits_a_previous_connections_account_context` | Una conexión nueva del mismo pool no hereda el contexto fijado en una conexión anterior — aísla el pooling en sí, no el código de sesión de la app por encima |
| `test_two_concurrent_connections_keep_independent_account_context` | Dos contextos de cuenta corriendo en paralelo real (`asyncio.gather`) en dos conexiones nunca se cruzan |
| `test_radar_worker_can_enumerate_accounts_but_still_needs_context_for_conversations` | El grant extra de `radar_worker` es específico de `accounts`, no se filtra a `conversations` |
| `test_radar_app_cannot_list_accounts_it_does_not_own` | `radar_app` no tiene el grant extra — confirma que no es una relajación global |

Estas 10 pruebas forman parte de la suite, pero requieren un Postgres accesible con los roles reales. La
ejecucion aislada docker compose run --rm --no-deps backend pytest -q las omite; ejecutalas aparte contra
el servicio db con docker compose run --rm backend pytest tests/test_rls_postgres.py -v.

## Consultas de verificación manual

```sql
-- Confirmar que radar_app no es superusuario ni tiene BYPASSRLS
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('radarin', 'radar_app', 'radar_worker');

-- Confirmar que radar_app no es propietario de ninguna tabla de la app
SELECT relname, pg_get_userbyid(relowner) AS owner FROM pg_class
WHERE relname IN ('conversations', 'profiles', 'accounts') AND relkind = 'r';

-- Confirmar FORCE ROW LEVEL SECURITY
SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'conversations';

-- Prueba de aislamiento (ejecutar como radar_app, no como radarin)
SET ROLE radar_app;  -- o conectar directamente con esas credenciales
SELECT set_config('app.account_id', '00000000-0000-0000-0000-000000000000', false);
SELECT count(*) FROM conversations;  -- 0, salvo que esa cuenta exista de verdad
```
