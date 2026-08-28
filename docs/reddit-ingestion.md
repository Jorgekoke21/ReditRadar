# Ingesta Reddit

La fuente de verdad son las comunidades activas de la base de datos. El perfil de vigilancia aporta idiomas y
max_age_hours; no hay una lista fija en el job.

Flujo:

Reddit listing -> normalización -> dedupe -> filtro determinista -> análisis/topics -> scoring/clasificación ->
persistencia -> alertas.

El job usa reddit_post_id, URL normalizada y hash existente. Guarda reddit_watermark_id y reddit_watermark_at por
comunidad, por lo que el estado no depende de memoria del proceso. El primer listado puede contener posts conocidos;
se cuentan como duplicados y nunca se crea una segunda conversación.

El filtro corre antes de get_analyzer; contenido eliminado, antiguo, spam, meme, promoción sin pregunta, exclusiones
y posts ya analizados no llegan al análisis costoso. El job registra recuperados, nuevos, duplicados, descartados,
analizados, guardados, recomendados y errores por comunidad.

sync_deleted_reddit_content consulta el endpoint oficial /api/info en lotes. Solo se purga el contenido temporal cuando
la respuesta contiene un marcador explícito de eliminación. Si el post no aparece en la respuesta, se conserva: la
API puede responder de forma parcial o estar temporalmente indisponible.

## Puente OAuth

Conectar: Configuración -> Conectar Reddit -> `GET /api/reddit/connect` devuelve `authorize_url` y un `state`
aleatorio que queda guardado en `reddit_oauth_states`, ligado a la cuenta, con 10 minutos de expiración y un solo
uso.

Reddit redirige el navegador a `REDDIT_REDIRECT_URI`, que apunta a la ruta del **frontend** `/reddit/callback`, no a
la API. Es deliberado: ese redirect no lleva cabecera `Authorization` -el token de sesión vive en el
almacenamiento de la aplicación, no en una cookie- así que el backend no podría autenticarlo. La página lee
`code` y `state` y los envía por `POST /api/reddit/callback` con la sesión del usuario. La cuenta se toma de esa
sesión; nunca del cuerpo de la petición ni del `state`, que viaja por el navegador y por tanto no es de fiar. El
`state` se marca como usado antes de intentar el intercambio, de modo que un `code` que falle no lo deja reutilizable.

Refresco: los access tokens de Reddit son de vida corta. Antes de cada ejecución de `fetch_reddit_conversations` y
de `sync_deleted_reddit_content`, `_ensure_fresh_access_token` refresca si el token expiró o le quedan menos de 5
minutos, vuelve a cifrar y persiste el nuevo token y su `expires_at`. Reddit no siempre devuelve un `refresh_token`
nuevo; cuando lo omite se conserva el anterior. Un fallo de refresco registra la ejecución como fallida y sigue
adelante con las demás cuentas: no detiene el worker ni el scheduler, y el siguiente tick reintenta. Ningún token
aparece en logs ni en mensajes de error.

Desconectar: `DELETE /api/reddit/connection` desactiva la conexión y borra los tokens cifrados. No borra
conversaciones ya ingeridas.

## Nombres de comunidad

`normalize_subreddit` es el único sitio que sabe quitar el prefijo: `SaaS`, `r/SaaS` y `/r/saas` son la misma
comunidad. Importa porque el nombre se usa como segmento de `/r/{nombre}/new` y porque la lista de vigilancia se
compara con el valor que devuelve la API; un nombre guardado como `r/SaaS` habría pedido `/r/r/SaaS/new` y habría
descartado todo lo de esa comunidad como `community_not_watched`.

## Estado de la verificación

IMPLEMENTADO Y PROBADO CON FAKE/MOCK: cliente, paginación, watermarks, dedupe, rate limiting, backoff, ambos jobs,
refresco de token, validación de `state`, callback y desconexión. Toda la cobertura usa adaptadores falsos o
transportes HTTP simulados.

PROBADO CONTRA REDDIT REAL: nada. No se ha hecho ninguna llamada real a Reddit.

## Activación

REDDIT_API_ENABLED sigue en false. Para activar en un entorno autorizado se necesitan aprobación de Reddit, OAuth
client id/secret, la redirect URI del frontend registrada en la app de Reddit exactamente igual que en
`REDDIT_REDIRECT_URI`, completar el flujo de conexión desde Configuración y una clave Fernet propia. El backend y
worker se niegan a iniciar Reddit si la clave de cifrado está vacía o es el fallback conocido.
