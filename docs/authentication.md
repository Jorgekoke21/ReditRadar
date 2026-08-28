# Autenticación

**Estado a 2026-07-27**: la aplicación usa Supabase Auth real (JWT verificado de verdad por el backend) por
defecto. Un modo de desarrollo explícito (`AUTH_MODE=development`) sigue existiendo para poder usar el proyecto
sin un proyecto Supabase real, pero está desactivado en producción por un guardia que impide arrancar el proceso si
se deja mal configurado. Ver `docs/rls.md` para cómo esta identidad se traduce en aislamiento real a nivel de base
de datos, y `docs/acceptance-audit.md` §4 para qué de esto está "probado con Supabase real" frente a "probado con
un proveedor JWT local".

## Los dos modos (`AUTH_MODE`)

| `AUTH_MODE` | Qué acepta el backend | Dónde se permite |
|---|---|---|
| `supabase` | Únicamente JWTs de Supabase, verificados de verdad (firma, `iss`, `aud`, `exp`, `sub`) | Producción y cualquier entorno con un proyecto Supabase real |
| `development` | Además de JWTs de Supabase (si `SUPABASE_JWT_SECRET` está configurado), tokens `dev:<uuid>` sin verificación real, emitidos por `POST /api/auth/dev-login` | Solo local/tests — nunca producción |

Reglas duras, aplicadas en código (`backend/app/main.py`, comprobado a nivel de arranque del proceso, no solo
documentado):

- Si `APP_ENV=production` y `AUTH_MODE=development` a la vez, **el proceso se niega a arrancar** —
  `RuntimeError` lanzado en el import de `app.main`, antes de que `uvicorn` levante nada.
  Prueba: `backend/tests/test_startup_guard.py::test_production_with_development_auth_refuses_to_start` (spawnea
  un subproceso real de Python que importa `app.main` y verifica `returncode != 0`).
- Si `AUTH_MODE=supabase` pero `SUPABASE_JWT_SECRET` está vacío, el proceso también se niega a arrancar — un
  entorno mal configurado no puede degradarse en silencio a "cualquiera entra".
  Prueba: `test_supabase_mode_without_jwt_secret_refuses_to_start`.
- El endpoint `POST /api/auth/dev-login` responde `403` si `AUTH_MODE=supabase`, independientemente de si alguien
  intenta llamarlo directamente.
- El formulario de login de desarrollo (`<details>` colapsado en `Login.tsx`) **no se renderiza en absoluto**
  cuando `config.auth_mode !== "development"` — no es solo que el botón esté deshabilitado, el DOM no lo contiene.
  Prueba E2E: `frontend/tests/e2e/auth.spec.ts::dev login is not offered when the backend reports AUTH_MODE=supabase`.

## Flujo de magic link (modo `supabase`)

1. El usuario introduce su email en `/login` y pulsa "Enviar enlace mágico".
2. El frontend llama a `supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: "<origin>/auth/callback" } })`
   vía `@supabase/supabase-js` (`frontend/src/lib/supabaseClient.ts`), usando la URL/clave anónima que el propio
   backend expone en `GET /api/auth/config` (nunca hardcodeadas en el bundle del frontend — así el backend sigue
   siendo la única fuente de verdad de qué proyecto Supabase está activo).
3. Estados de UI cubiertos explícitamente en `Login.tsx` / `lib/auth.tsx`:
   - **Enviando enlace**: botón deshabilitado, texto "Enviando enlace…".
   - **Enlace enviado**: mensaje de confirmación "Enlace enviado. Revisa tu correo y haz clic para entrar.".
   - **Error de configuración**: si `auth_mode=supabase` pero el backend no expone `supabase_url`/`supabase_anon_key`
     válidos (o `/api/auth/config` no responde), se muestra una pantalla de error accionable en vez de un login
     roto en silencio.
   - **Sesión expirada**: `api.ts` intercepta cualquier `401` de la API y redirige a `/login?reason=expired`, que
     `Login.tsx` muestra como un aviso ("Tu sesión ha expirado. Vuelve a iniciar sesión.").
   - **Token inválido**: Supabase redirige a `/auth/callback` con `error`/`error_description` en la URL cuando el
     enlace ya se usó o expiró; `AuthCallback.tsx` lo detecta y muestra "Enlace inválido o expirado: …".
4. Al pulsar el enlace del correo, Supabase redirige a `/auth/callback`. `detectSessionInUrl: true` hace que
   `@supabase/supabase-js` procese el fragmento de la URL por su cuenta y dispare `onAuthStateChange("SIGNED_IN")`,
   que es lo que realmente puebla la sesión de la app (`AuthCallback.tsx` solo muestra el estado de carga/error
   mientras eso ocurre).
5. La sesión se persiste por `@supabase/supabase-js` en `localStorage` (`persistSession: true`) bajo la clave
   `sb-<ref>-auth-token`, y se recupera automáticamente en cada carga de página vía `supabase.auth.getSession()` —
   sin necesitar un nuevo login. `autoRefreshToken: true` renueva el `access_token` en segundo plano antes de que
   expire.
6. Logout (`Sidebar.tsx` → `logout()`): llama a `supabase.auth.signOut()` y, **incondicionalmente** (incluso si esa
   llamada falla por red), limpia el estado local (`localStorage`, token activo en memoria, perfil) — un usuario
   siempre puede cerrar sesión en este navegador aunque Supabase esté inalcanzable.

## Verificación del JWT en el backend

`backend/app/core/security.py::verify_supabase_jwt` — nunca confía en nada que venga del cliente sin verificar:

```python
payload = jwt.decode(
    token,
    settings.supabase_jwt_secret,
    algorithms=["HS256"],
    audience="authenticated",
    options={"require_sub": True, "require_exp": True},
)
if settings.supabase_issuer and payload.get("iss") != settings.supabase_issuer:
    raise HTTPException(401, "Token issuer does not match this Supabase project")
```

Se comprueba explícitamente:

| Comprobación | Cómo | Resultado si falla |
|---|---|---|
| Firma HS256 con `SUPABASE_JWT_SECRET` | `jose.jwt.decode` | 401 |
| `aud == "authenticated"` | `audience="authenticated"` en `jwt.decode` | 401 |
| `iss == {SUPABASE_URL}/auth/v1` | Comparación explícita tras decodificar | 401 |
| `exp` presente y no vencido | `require_exp: True` + verificación automática de `jose` | 401 |
| `sub` presente | `require_sub: True` | 401 |

`user_id` sale **exclusivamente** de `payload["sub"]` — nunca de un header, de un parámetro de query ni del cuerpo
de la petición. `account_id` nunca lo envía el cliente: sale de `profiles.account_id`, resuelto a partir de ese
`user_id` ya verificado (`get_current_account_id` → `get_current_principal` → `_resolve_profile`).

Probado en `backend/tests/test_auth_jwt.py` (12 tests): firma incorrecta, JWT expirado, `iss` incorrecto, `aud`
incorrecto, sin `sub`, token malformado, sin token, y el camino feliz con aprovisionamiento. Además,
`test_backend_ignores_client_supplied_account_id` prueba explícitamente que un `account_id` inyectado en el cuerpo
de una petición (`POST /api/conversations/manual`) se ignora — la fila creada pertenece siempre a la cuenta del
token, nunca a la que el cliente intentó forzar.

## `AuthenticatedPrincipal`

```python
@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: uuid.UUID
    account_id: uuid.UUID
    email: str | None = None
```

Es la única forma en que el resto del backend conoce "quién hace esta petición" — ningún router lee `sub`, headers
de desarrollo, ni ningún campo de la petición para deducir identidad. `get_current_account_id` (usado por los 11
routers) y `get_current_profile` dependen ambos de `get_current_principal`, que es lo único que habla con
`verify_supabase_jwt`/el token `dev:`.

## Aprovisionamiento de cuentas (`profiles` / `accounts`)

- **Identidad = `profiles.id` = el UUID de Supabase Auth (`auth.users.id` / el `sub` del JWT). Nunca el email.**
  `profiles.email` es una columna informativa, sin restricción de unicidad — dos identidades distintas (p. ej. un
  login de desarrollo y un login Supabase real) pueden compartir email sin fusionarse en la misma cuenta. Esto se
  verificó explícitamente como bug real durante esta fase: la columna tenía originalmente `unique=True`, lo que
  lanzaba un `IntegrityError` (500 crudo) en cuanto dos identidades coincidían en email — corregido en la migración
  `0004_profiles_email_not_unique.py`. Prueba:
  `test_provisioning_never_merges_accounts_by_email`.
- **Relación**: `auth.users.id` (Supabase) → `profiles.id` (mismo UUID) → `profiles.account_id` → `accounts.id`.
  Una cuenta por usuario hoy (no hay UI de invitar a un segundo usuario a la misma cuenta); el modelo de datos no
  lo impide para el futuro, pero esta fase no implementa multiusuario por cuenta.
- **Primer login**: si no existe un `Profile` con ese `id`, se crea una `Account` nueva (`name="My workspace"`) y un
  `Profile` que la referencia, dentro de la misma transacción, antes de responder. Es decir: JWT válido de un
  usuario nunca antes visto **nunca** se rechaza por "no aprovisionado" — se aprovisiona en el acto.
- **Idempotencia**: logins repetidos con el mismo `sub` resuelven siempre al mismo `account_id` — nunca crean una
  segunda cuenta. Prueba: `test_provisioning_is_idempotent_across_repeated_logins`.
- **JWT válido pero usuario nunca antes visto**: cubierto por el punto de "primer login" — no es un caso de error,
  es el camino normal de aprovisionamiento. Prueba: `test_valid_user_without_a_profile_gets_provisioned_on_first_login`
  (verifica también, contra la base de datos directamente, que la `Account` y el `Profile` realmente existen tras
  la petición — no solo que la respuesta HTTP fue 200).

## Variables de entorno relevantes

| Variable | Efecto |
|---|---|
| `AUTH_MODE` | `supabase` \| `development`. Ver tabla arriba. |
| `APP_ENV` | Si es `production`, activa el guardia de arranque que rechaza `AUTH_MODE=development`. |
| `SUPABASE_URL` | Proyecto Supabase; también usado para derivar `iss` esperado (`{SUPABASE_URL}/auth/v1`). |
| `SUPABASE_ANON_KEY` | Expuesta vía `GET /api/auth/config` al frontend, para construir el cliente `supabase-js`. |
| `SUPABASE_JWT_SECRET` | Secreto HS256 usado para verificar la firma de los JWTs. Sin él, `AUTH_MODE=supabase` no arranca. |

Ninguna de estas se lee nunca desde el frontend vía `VITE_*` — el frontend las obtiene siempre de
`GET /api/auth/config` (público, sin autenticación) para que el backend sea la única fuente de verdad.

## Entorno local: qué opción se usó y por qué

Se usó la **opción B** (proveedor JWT local compatible para tests) combinada con el modo desarrollo (opción C) para
la experiencia interactiva del navegador:

- **Tests automatizados** (`backend/tests/jwt_helpers.py`, `frontend/tests/e2e/helpers.ts::mintTestSupabaseJwt`):
  ambos minan JWTs HS256 con exactamente el mismo contrato que `verify_supabase_jwt` comprueba (mismo secreto,
  mismo `iss`, mismo `aud`, mismo `sub`), firmados localmente sin ningún servidor Supabase real. Esto ejercita el
  código de verificación real, no un mock de él — ver la nota de clasificación en `docs/acceptance-audit.md`. La
  prueba E2E `a genuine (locally-signed) Supabase session recovered from storage logs the user in`
  (`frontend/tests/e2e/auth.spec.ts`) va un paso más allá: siembra en `localStorage` una sesión con la misma forma
  exacta que `@supabase/supabase-js` persistiría tras un login real, para probar la recuperación de sesión sin
  depender de la disponibilidad de red.
- **Navegador interactivo local** (`AUTH_MODE=development` en `.env`): como no existe un proyecto Supabase real
  para este entorno, `docker compose up` deja el formulario de login de desarrollo disponible (colapsado bajo
  "Usar acceso de desarrollo en su lugar" cuando también hay una config de Supabase de prueba configurada). El
  texto bajo el formulario lo etiqueta explícitamente: "Este entorno acepta también un acceso de desarrollo sin
  verificación, solo para uso local — nunca disponible cuando `AUTH_MODE=supabase`." **En ningún momento se
  presenta este modo como si fuera Supabase Auth real.**
- No se creó un proyecto Supabase real para esta fase (no hay credenciales de un proyecto real disponibles en este
  entorno) — por eso ninguna afirmación de este documento dice "probado con Supabase real". Ver
  `docs/acceptance-audit.md` §4 para la clasificación explícita de cada prueba.
