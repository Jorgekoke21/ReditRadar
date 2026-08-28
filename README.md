# Radar de Conversaciones

Herramienta interna de Radarin para vigilar Reddit en busca de conversaciones donde aportar valor real, priorizarlas
con una puntuación explicable, preparar borradores de respuesta y llevar seguimiento de resultados.

**La aplicación nunca publica en Reddit.** Solo prepara información y borradores; la publicación siempre la hace una
persona manualmente desde Reddit.

Proyecto independiente del repositorio principal de Radarin (`radarin-conversation-radar`), pensado para uso interno.

## Arranque rápido (Docker Compose)

Requisitos: Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

Esto levanta, en un solo comando:

- **db**: Postgres 16, expuesto en el host en `localhost:5544`.
- **backend**: FastAPI, aplica las migraciones de Alembic y siembra los datos de demostración automáticamente al
  arrancar, luego sirve la API en `http://localhost:8010` (Swagger/OpenAPI en `http://localhost:8010/docs`).
- **worker**: proceso APScheduler independiente que ejecuta los 8 jobs programados (ver `docs/architecture.md`).
- **frontend**: Vite + React en `http://localhost:5180`.

Al entrar en `http://localhost:5180` verás la pantalla de login. El `.env` de este repo trae `AUTH_MODE=development`
más una configuración Supabase de prueba (sin proyecto real detrás), así que el formulario ofrece tanto un enlace
mágico simulado como un acceso de desarrollo colapsado bajo "Usar acceso de desarrollo en su lugar": introduce
cualquier correo (por ejemplo `demo@radarin.local`, la cuenta que ya tiene los 20 ejemplos de demostración) y se
abre una sesión local sin enviar ningún email real. Ver `docs/authentication.md` para el detalle de ambos modos.

## Arranque sin Docker (opcional)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
# Necesitas un Postgres accesible en DATABASE_URL (o usa sqlite+aiosqlite:///./local.db para probar rápido)
alembic upgrade head
python -m app.seeds.demo_data
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Modos de funcionamiento

| Modo | Requiere credenciales | Qué hace |
|---|---|---|
| **Demo** | No | 20 conversaciones ficticias precargadas, marcadas como tal en la interfaz. |
| **Manual** | No | Pega una conversación o importa un CSV; se analiza igual que si viniera de Reddit. |
| **Reddit API** | Sí (OAuth aprobado) | Desactivado por defecto (`REDDIT_API_ENABLED=false`). Ver `docs/reddit-access-request.md`. |

La aplicación es completamente utilizable sin IA y sin la API de Reddit — ver `docs/manual-mode.md` y
`docs/reddit-compliance.md`.

## Tests

Backend: suite SQLite/FakeReddit y tests RLS opcionales (ver cifras de la ultima ejecucion en docs/testing.md):

```bash
cd backend
docker compose run --rm -e DATABASE_URL=sqlite+aiosqlite:///./test_radar.db backend pytest -q
```

Frontend E2E, contra el stack real levantado con `docker compose up` (37 tests):

```bash
cd frontend
npx playwright test
```

Ver `docs/testing.md` para el detalle de qué cubre cada uno y `docs/acceptance-audit.md` para el resultado de la
última auditoría completa (qué está realmente probado, qué es simulado y qué queda pendiente).

## Estado real de auth y RLS (léelo antes de asumir nada)

El login usa **Supabase Auth real** por defecto (`AUTH_MODE=supabase`): el backend verifica de verdad la firma,
emisor, audiencia y expiración de cada JWT (`backend/app/core/security.py`), y nunca confía en un `account_id`
enviado por el cliente. Un modo de desarrollo explícito (`AUTH_MODE=development`) sigue existiendo para poder
trabajar sin un proyecto Supabase real — pero el backend **se niega a arrancar** si detecta
`APP_ENV=production` con `AUTH_MODE=development`, y el formulario de login de desarrollo no se renderiza en
absoluto cuando el modo activo es `supabase`. Las políticas RLS de Postgres **protegen de verdad** hoy: el backend
se conecta con un rol (`radar_app`/`radar_worker`) que no es propietario de las tablas y no tiene `BYPASSRLS`,
verificado con consultas directas a Postgres (no por inferencia) en `backend/tests/test_rls_postgres.py`. Detalle
completo, con qué está probado contra Supabase real frente a un proveedor JWT local, en `docs/authentication.md`,
`docs/rls.md` y `docs/acceptance-audit.md`.

## Documentación

- [`docs/architecture.md`](docs/architecture.md) — arquitectura, stack, decisiones.
- [`docs/data-model.md`](docs/data-model.md) — tablas, retención, RLS.
- [`docs/authentication.md`](docs/authentication.md) — Supabase Auth real, modo desarrollo, aprovisionamiento.
- [`docs/rls.md`](docs/rls.md) — roles de base de datos, políticas RLS, pooling, pruebas reproducibles.
- [`docs/reddit-compliance.md`](docs/reddit-compliance.md) — cumplimiento y estado de la integración con Reddit.
- [`docs/deployment.md`](docs/deployment.md) — despliegue en Vercel + Render + Supabase.
- [`docs/manual-mode.md`](docs/manual-mode.md) — cómo funciona el modo manual y el CSV.
- [`docs/reddit-access-request.md`](docs/reddit-access-request.md) — borrador de solicitud de acceso a Reddit.
- [`docs/testing.md`](docs/testing.md) — qué prueban los tests.
- [`docs/progress.md`](docs/progress.md) — bitácora de construcción del proyecto.
- [`docs/acceptance-audit.md`](docs/acceptance-audit.md) — auditoría de aceptación con evidencia reproducible,
  fuente de verdad sobre qué está realmente completo, parcial, simulado o pendiente.

## Variables de entorno

Ver [`.env.example`](.env.example). Ningún secreto real está incluido en el repositorio.
