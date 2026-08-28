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

## Activación

REDDIT_API_ENABLED sigue en false. Para activar en un entorno autorizado se necesitan aprobación de Reddit, OAuth
client id/secret, redirect URI, un token OAuth guardado por el callback y una clave Fernet propia. El backend y worker
se niegan a iniciar Reddit si la clave de cifrado está vacía o es el fallback conocido.
