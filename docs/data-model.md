# Modelo de datos

19 tablas, todas con `id` UUID, `created_at`/`updated_at` (donde aplica), e índices en toda foreign key. Definidas en
`backend/app/models/*.py`, migradas en `backend/alembic/versions/27e66f7e965c_initial_schema.py`.

## Tablas

| Tabla | Qué guarda |
|---|---|
| `accounts` | Límite de propiedad/facturación. Todo cuelga de `account_id`. |
| `profiles` | Un perfil por usuario de Supabase Auth (`profiles.id == auth.users.id`). `email` no es único — la identidad es el UUID, nunca el email, ver `docs/authentication.md`. |
| `communities` | Subreddits vigilados: prioridad, idioma, reglas, notas, contadores. |
| `watch_profiles` / `watch_profile_communities` | Perfiles de vigilancia y su M2M con comunidades. |
| `topics` / `topic_keywords` / `topic_exclusions` | Temas vigilados, sus palabras clave y exclusiones. |
| `conversations` | Fila central: datos operativos + contenido temporal (`raw_*`). Ver retención abajo. |
| `conversation_analysis` | Snapshot del último análisis (reglas o IA) — 1:1 con `conversations`, se sobrescribe al reanalizar. |
| `conversation_scores` | Histórico de cálculos de puntuación (una fila por cada recálculo). |
| `reply_drafts` | Los borradores (educativo / mención suave / mención directa) de una conversación. |
| `conversation_actions` | Log de acciones append-only (analizada, guardada, descartada, restaurada, etc.). |
| `conversation_outcomes` | Resultado registrado manualmente por el usuario (1:1 con `conversations`). |
| `alert_settings` / `alert_deliveries` | Configuración de alertas y cada correo generado (enviado o solo previsualizado). |
| `scheduled_job_runs` | Bitácora de cada ejecución de job: estado, procesados, errores, duración. |
| `audit_logs` | Log genérico de eventos (reservado para auditoría futura). |
| `reddit_connections` | Estado OAuth (tokens cifrados) de la integración de solo lectura con Reddit. |

## Deduplicación (idempotencia)

`app/services/dedupe.py` calcula, para cada conversación entrante:

1. `reddit_post_id` (si viene de la API de Reddit) — coincidencia exacta.
2. `url_normalized` (esquema+host+path, sin `www.`, sin slash final, sin query string).
3. `dedupe_hash` = sha256(`subreddit` + título normalizado *sin acentos* + fecha de publicación).

`_create_and_analyze` (usado por importación manual, CSV y — cuando esté activa — la API de Reddit) primero busca
una fila existente por estas claves y la devuelve tal cual si existe, en vez de crear una nueva. Importar la misma
conversación dos veces nunca duplica una fila (cubierto por `tests/test_dedupe.py` y `tests/test_csv_import.py`).

## Retención y modelo de privacidad

Cada conversación separa dos categorías de datos en la misma fila (no en tablas distintas, por simplicidad — el
particionado real ocurre a nivel de qué *columnas* se limpian, no de qué tabla vive el dato):

- **Contenido original temporal** (`raw_title`, `raw_body`, `raw_author`): lo que vino de Reddit o lo que el
  usuario pegó a mano. Sujeto a `expires_at` = `detected_at + RAW_CONTENT_RETENTION_HOURS` (48h por defecto).
- **Datos operativos** (todo lo demás: `id`, `url`, `subreddit`, `summary`, `score_total`, `recommended_action`,
  acciones, resultado): no expiran nunca — son necesarios para las métricas de `/history`, la deduplicación futura
  y el resultado registrado.

El job `purge_expired_reddit_content` (corre cada hora vía el worker, y también expuesto en `/diagnostics` para
ejecución manual) pone a `NULL` los tres campos `raw_*` y marca `raw_purged_at` en cuanto `expires_at` ya pasó. La
ficha de conversación (`ConversationDetail.raw_purged`) muestra un aviso en vez del texto original una vez purgado,
y usa `summary` como sustituto no identificativo del título (`Conversation.display_title`).

El usuario también puede forzar el borrado inmediato desde la ficha (`DELETE /api/conversations/{id}/raw-content`).

**Excepción deliberada**: las 20 conversaciones de demostración tienen `expires_at = NULL` — no son contenido real
de Reddit, son texto ficticio de ejemplo, así que no tiene sentido purgarlas; se marcan con `is_demo=true` y la
interfaz las etiqueta visualmente como "Ejemplo ficticio" en vez de ocultarlo.

## Row Level Security (RLS)

RLS está activo **con efecto real**, verificado empíricamente contra Postgres (no solo por diseño). El backend usa
un rol (`radar_app`, o `radar_worker` para el proceso de jobs) que **no** es propietario de las tablas y **no**
tiene `BYPASSRLS` — a diferencia de `radarin`, que solo Alembic usa para migraciones. Cada tabla con datos de
cuenta tiene una política basada en `current_setting('app.account_id', true)` (o `app.user_id` para el caso
especial de `profiles`, ver `docs/rls.md`), fijado por el backend con `SELECT set_config(..., true)` (equivalente a
`SET LOCAL`) al principio de cada transacción, y `FORCE ROW LEVEL SECURITY` aplicado como defensa en profundidad
adicional.

Prueba directa reproducible contra el Postgres real (conectando como `radar_app`, no como `radarin`):

```sql
SELECT set_config('app.account_id', '00000000-0000-0000-0000-000000000000', false);  -- UUID que no existe
SELECT count(*) FROM conversations;  -- 0
```

Documentación completa (roles, migración, el bug circular de `profiles` que se corrigió, cómo se evita fuga de
contexto entre conexiones del pool, y las 10 pruebas automatizadas que lo verifican) en **`docs/rls.md`**.

La separación entre cuentas sigue reforzada también a nivel de aplicación (todos los routers dependen de
`get_current_account_id`, deducido del token JWT verificado, nunca de un parámetro de la petición) — pero ya no es
la única capa: si un filtro `account_id` se olvidara en algún endpoint futuro, RLS seguiría negando el acceso a
filas fuera de la cuenta activa. Verificado con pruebas de dos cuentas en `tests/test_ownership.py` (backend, a
nivel de aplicación) y `frontend/tests/e2e/ownership.spec.ts` (navegador real), además de las pruebas RLS directas
contra Postgres en `backend/tests/test_rls_postgres.py`.

## Constraints y unicidad relevantes

- `conversations`: única por `(account_id, reddit_post_id)` y por `(account_id, dedupe_hash)`.
- `communities` / `topics`: únicos por `(account_id, name)`.
- `watch_profile_communities`: único por `(watch_profile_id, community_id)`.
- Enums (`ConversationState`, `RecommendedAction`, `PromotionRisk`, etc.) están implementados como
  `Enum(..., native_enum=False)`: se guardan como `VARCHAR` con `CHECK` constraint — funciona igual en Postgres y en
  SQLite (necesario para que la suite de tests no dependa de Postgres), y sigue restringiendo los valores válidos a
  nivel de base de datos.
