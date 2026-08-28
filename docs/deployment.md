# Despliegue

## Local (recomendado para desarrollo y para revisar este proyecto)

```bash
cp .env.example .env
docker compose up --build
```

Ver `README.md` para el detalle de qué contenedor hace qué.

## Producción objetivo: Supabase + Vercel + Render

Esta es la arquitectura para la que está preparado el proyecto. **No se ha desplegado realmente** en este ejercicio
— no existen credenciales de Supabase/Vercel/Render del usuario — pero el código no tiene ninguna dependencia de
"local únicamente" que lo impida.

### 1. Base de datos + Auth: Supabase

1. Crear un proyecto en Supabase.
2. Copiar `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_JWT_SECRET` (Project Settings → API / Auth).
3. Apuntar `DATABASE_MIGRATION_URL` a la cadena de conexión de Supabase Postgres con un rol propietario (usar el
   *connection pooler* de Supabase en producción, no la conexión directa). **No** usar este rol para
   `DATABASE_APP_URL`/`DATABASE_WORKER_URL`.
4. Ejecutar `alembic upgrade head` contra `DATABASE_MIGRATION_URL` — aplica el esquema, crea los roles `radar_app`/
   `radar_worker` (sin `BYPASSRLS`, sin ser propietarios de las tablas) y las políticas RLS efectivas
   (`docs/rls.md`).
5. Apuntar `DATABASE_APP_URL`/`DATABASE_WORKER_URL` a esa misma base de datos, pero con las credenciales de
   `radar_app`/`radar_worker` que la migración acaba de crear (`RADAR_APP_DB_PASSWORD`/`RADAR_WORKER_DB_PASSWORD`
   — cambiar los valores de desarrollo antes de desplegar).
6. Activar el proveedor de email "Magic Link" en Supabase Auth (Authentication → Providers → Email).
7. Poner `AUTH_MODE=supabase` y `APP_ENV=production`. El backend se niega a arrancar si detecta
   `APP_ENV=production` junto con `AUTH_MODE=development` (`app/main.py`), así que un despliegue mal configurado
   falla de forma ruidosa en vez de exponer el login de desarrollo — ver `docs/authentication.md`.

### 2. Frontend: Vercel

1. Importar el repo, `Root Directory` = `frontend/`.
2. Build command: `npm run build`. Output: `dist/`.
3. Variable de entorno: `VITE_API_URL` = URL pública del backend en Render. No hace falta ninguna variable
   `VITE_SUPABASE_*` — el frontend obtiene `supabase_url`/`supabase_anon_key` de `GET /api/auth/config`
   (`src/lib/auth.tsx`), así que el backend es la única fuente de verdad de qué proyecto Supabase está activo.
4. El login real por magic link (`@supabase/supabase-js`, `signInWithOtp`) ya está integrado
   (`src/lib/supabaseClient.ts`, `src/lib/auth.tsx`, `src/pages/AuthCallback.tsx`) — no requiere cambios de código
   para desplegarse, solo que el backend reporte `auth_mode=supabase` con una configuración Supabase válida.
   Recordar añadir `<dominio de Vercel>/auth/callback` a las Redirect URLs permitidas en Supabase Auth (Authentication
   → URL Configuration), o el enlace mágico redirigirá a una URL rechazada.

### 3. Backend + worker: Render

Dos servicios a partir del mismo `backend/Dockerfile`:

- **Web Service** (`backend`): comando de arranque
  `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Background Worker** (`worker`): comando de arranque `python -m app.worker`.

Variables de entorno en ambos: todas las de `.env.example` salvo `APP_URL`/`VITE_API_URL` (esas son del frontend).
Especialmente:

- `DATABASE_MIGRATION_URL` (solo lo usa el paso de arranque `alembic upgrade head`), `DATABASE_APP_URL` (backend),
  `DATABASE_WORKER_URL` (worker) → Postgres de Supabase, cada uno con el rol correspondiente (ver paso 1 arriba).
- `AUTH_MODE=supabase`, `APP_ENV=production`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`.
- `REDDIT_API_ENABLED=false` hasta tener aprobación (ver `docs/reddit-compliance.md`).
- `AI_ANALYSIS_ENABLED=false` hasta tener una clave de proveedor de IA real.
- `EMAIL_PROVIDER=console` hasta configurar SMTP o Resend.
- `RAW_CONTENT_RETENTION_HOURS=48`.
- `REDDIT_TOKEN_ENCRYPTION_KEY` → generar un secreto propio (`python -c "import secrets;print(secrets.token_urlsafe(32))"`).

### 4. CORS

`app/main.py` restringe `CORSMiddleware` a `settings.app_url` + `localhost:5180`. En producción, poner `APP_URL` al
dominio real de Vercel antes de desplegar, o el frontend desplegado no podrá llamar a la API.

## Variables que faltan para un despliegue 100% funcional

Ninguna de estas bloquea el uso en Demo/Manual — solo desbloquean funcionalidad opcional:

| Variable | Desbloquea |
|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` de un **proyecto Supabase real** | El login por magic link ya está implementado y probado con un proveedor JWT local (`docs/authentication.md`); lo único que falta para "probado con Supabase real" es un proyecto Supabase real contra el que ejecutarlo — no hay cambio de código pendiente. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_API_ENABLED=true` | Conexión OAuth (`/api/reddit/connect`). **No** desbloquea sincronización automática por sí solo: fetch_reddit_conversations está implementado, pero requiere callback OAuth, conexión activa, watermark y validación operativa — ver `docs/reddit-compliance.md`. |
| `AI_API_KEY`, `AI_PROVIDER`, `AI_ANALYSIS_ENABLED=true` | Análisis vía IA en vez de (o además de) reglas. |
| `SMTP_*` o `RESEND_API_KEY`, `EMAIL_PROVIDER=smtp`/`resend` | Envío real de los correos (hoy: bandeja de previsualización). |
