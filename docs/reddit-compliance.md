# Cumplimiento con Reddit

**Estado actual: el código de ingesta está preparado, pero la integración permanece desactivada
(REDDIT_API_ENABLED=false) y no existen credenciales/aprobación configuradas.** Los tests usan exclusivamente
FakeRedditClient; no se hizo ninguna llamada real a Reddit. Este documento no afirma que Reddit haya aprobado esta
aplicación.

## Principios seguidos (obligatorios, sección 3 del encargo)

| # | Principio | Cómo se cumple |
|---|---|---|
| 1 | No scraping HTML | No hay ningún cliente HTTP apuntando a `www.reddit.com` salvo `app/services/reddit_client.py`, que solo usa `oauth.reddit.com` con un token Bearer. |
| 2 | No Selenium/Playwright/Puppeteer para recolectar publicaciones | Ningún navegador automatizado se usa para leer Reddit. (Playwright sí se usó puntualmente durante el desarrollo para verificar visualmente *esta propia interfaz*, nunca para tocar Reddit.) |
| 3 | No endpoints privados/no documentados | Solo se usan `/api/v1/authorize`, `/api/v1/access_token` (grants `authorization_code` y `refresh_token`), `/r/{subreddit}/new` y `/api/info`, todos parte de la API pública documentada de Reddit. |
| 4 | No publicar comentarios automáticamente | No existe ningún endpoint ni botón que publique. Ver "Botones permitidos" abajo. |
| 5 | No votar automáticamente | No implementado, ni el scope `vote` se solicita. |
| 6 | No mensajes privados | No implementado, ni el scope `privatemessages` se solicita. |
| 7 | No gestionar varias cuentas | Diseño single-user; una única `RedditConnection` por cuenta. |
| 8 | No entrenar modelos con contenido de Reddit | El contenido de Reddit nunca sale del par petición/respuesta hacia el proveedor de IA (cuando está activo) más que el título/cuerpo/subreddit/idioma necesarios para clasificar; no se usa para fine-tuning en ningún punto del código. |
| 9 | No inferir características sensibles | El analizador solo extrae: tipo de audiencia (a partir del subreddit), problema, intención, tema, riesgo promocional. Nunca perfila a la persona autora. |
| 10 | No almacenar perfiles personales innecesarios | `raw_author` es el único campo con un identificador de usuario de Reddit, y se purga a las 48h como el resto del contenido temporal (ver `docs/data-model.md`). |
| 11 | Solo integración oficial aprobada | `reddit_client.py` implementa exclusivamente el flujo OAuth documentado (`authorization_code` con `duration=permanent`, y `refresh_token` para renovar). |
| 12 | Integración desactivada hasta tener aprobación | `REDDIT_API_ENABLED=false` por defecto; cada función pública de `reddit_client.py` lanza `RedditIntegrationDisabled` si la bandera está apagada, sin excepción. `GET /api/reddit/connect` devuelve `403` mientras esté desactivada. |

## Clasificación por capacidad

| Capacidad | Estado |
|---|---|
| Puerta de activación | Completa: REDDIT_API_ENABLED=false rechaza antes de HTTP. |
| OAuth | Implementado y probado con Fake/Mock (autorizacion, `state` de un solo uso ligado a la cuenta, intercambio, refresco y desconexion); no probado contra Reddit real. Scopes de solo lectura. |
| Fetch oficial | Implementado en fetch_reddit_conversations; probado con FakeRedditClient, no con Reddit real. |
| Paginación y watermark | Implementados; watermark persistente por comunidad evita reprocesar tras reinicio. |
| Filtro, análisis, scoring y dedupe | Reutilizan el pipeline existente y se ejecutan antes de cualquier LLM. |
| Rate limits | Se parsean x-ratelimit-remaining, x-ratelimit-used y x-ratelimit-reset. |
| 429/5xx/timeouts | Backoff exponencial con jitter y máximo de reintentos; sin retry indefinido. |
| Deleted sync | Parcial por diseño: /api/info marca solo eliminaciones explícitas; ausencias no se consideran borrado. |
| Tokens | Cifrados en reposo; la app/worker rechaza clave vacía o fallback conocido si Reddit está activado. |
| Publicar, votar, DM | No implementados; no existen endpoints ni scopes para ello. |

## Scopes solicitados

Solo lectura mínima: `identity`, `read`, `mysubreddits` (`READ_ONLY_SCOPES` en `reddit_client.py`). Nunca se solicita
`submit`, `privatemessages`, `vote`, `modcontim`/moderación ni ningún scope de escritura.

## User-Agent

Configurable vía `REDDIT_USER_AGENT`, con un valor por defecto transparente:
`radarin-conversation-radar/0.1 (internal tool; contact: you@example.com)`. Nunca se enmascara ni se rota.

## Rate limits y backoff

_get_with_backoff limita los reintentos, aplica backoff exponencial con jitter, respeta retry-after cuando existe y
trata timeout/transporte como errores temporales. Cada respuesta conserva x-ratelimit-remaining, x-ratelimit-used
y x-ratelimit-reset en métricas operativas. No hay retry indefinido ni fallback a scraping. La semántica de la cuota
debe validarse de nuevo al activar acceso autorizado.

## Botones permitidos en la interfaz (y por qué no hay más)

La ficha de conversación (`/conversations/:id`) solo ofrece:

- **Copiar respuesta** — copia el borrador al portapapeles.
- **Editar** — el textarea del borrador es editable directamente.
- **Abrir en Reddit** — abre la URL original en una pestaña nueva; la persona pega y publica manualmente.
- **Guardar / Marcar como respondida / Descartar** — solo cambian el estado interno de la conversación.

**No existe ningún botón de "Publicar"** en ninguna pantalla del proyecto. Publicar en Reddit es, por diseño,
un acto humano que ocurre fuera de esta aplicación.

## Qué falta para activar el modo Reddit API

1. Aprobación oficial de acceso a la Data API.
2. REDDIT_CLIENT_ID y REDDIT_CLIENT_SECRET de una aplicación OAuth autorizada.
3. REDDIT_REDIRECT_URI desplegada y registrada.
4. REDDIT_TOKEN_ENCRYPTION_KEY fuerte, propia, no vacía y distinta del fallback.
5. Migrar la base de datos, ejecutar el callback OAuth y guardar una conexión activa.
6. Configurar JOB_ADMIN_EMAILS en producción y hacer una prueba controlada respetando la documentación vigente.

La documentación de Reddit (Responsible Builder Policy, Developer Terms, Data API Terms y OAuth) debe revisarse
de nuevo inmediatamente antes de activar el entorno real. No se ha llamado a Reddit ni se ha afirmado aprobación.

## Estado de esta fase

- OAuth: implementado de extremo a extremo (conectar, callback, refresco automatico, desconectar) y probado con Fake/Mock; no probado contra Reddit real.
- Fetch, paginación, rate limits y backoff: implementados y probados con fake; integración real bloqueada por aprobación/credenciales.
- Cursor/watermark: implementado en communities.reddit_watermark_* y persistente ante reinicios.
- Ingesta, dedupe, filtro, análisis, scoring y alertas: reutilizan el pipeline existente; probado con SQLite/FakeReddit.
- Deleted sync: implementado solo para marcadores explícitos devueltos por /api/info; una respuesta ausente no se finge como borrado.
- Publicación, DM y votos: no implementados y no deben añadirse.
