# Borrador de solicitud de acceso a la API de Reddit

> Este documento es un borrador de referencia para cuando se solicite acceso oficial a la Data API de Reddit.
> **No implica que Reddit haya aprobado esta aplicación.** Antes de enviarlo, revisar la documentación vigente en
> ese momento (Responsible Builder Policy, Developer Terms, Data API Terms, Data API Wiki, OAuth) — puede haber
> cambiado desde que se escribió este borrador.

---

**Nombre del proyecto**: Radar de Conversaciones (`radarin-conversation-radar`)

**Propietario**: [nombre / empresa del propietario de Radarin — completar antes de enviar]

**Tipo de uso**: Interno. Esta aplicación no es un producto que se ofrezca a terceros ni se redistribuye; la usa
únicamente el equipo de Radarin para su propio trabajo de desarrollo de negocio.

**Finalidad comercial, de forma transparente**: Radarin es un SaaS que ayuda a agencias, freelancers y consultores
a encontrar negocios locales con potencial y priorizar a quién contactar. Esta herramienta vigila subreddits
públicos relacionados con ese problema (agencias, freelance, SEO local, SaaS, emprendimiento) para que una persona
del equipo pueda, cuando corresponda, aportar valor real en esas conversaciones — y, quien pregunta explícitamente
por herramientas, sepa de forma transparente que Radarin existe. La aplicación **no publica nada automáticamente**:
solo prepara información para que una persona decida y actúe manualmente en Reddit.

**Comunidades que se vigilarán** (lista inicial, editable por el usuario desde `/communities`):

Potenciales clientes: r/agency, r/localseo, r/web_design, r/freelance, r/sales, r/marketing, r/smallbusiness.

Aprendizaje/construcción: r/SaaS, r/SaaSDevelopers, r/SideProject, r/startups, r/Entrepreneur,
r/EntrepreneurRideAlong, r/thesidehustle.

**Datos que se necesitan**: listados de publicaciones nuevas (`GET /r/{subreddit}/new`) de las comunidades
anteriores — título, cuerpo, autor, subreddit, fecha, número de comentarios, puntuación. Ningún dato de mensajes
privados, ni de otros usuarios fuera de esas publicaciones públicas.

**Frecuencia prevista**: consulta cada 15 minutos por comunidad vigilada (job `fetch_reddit_conversations`),
respetando los límites de tasa comunicados en las cabeceras de la respuesta y con backoff exponencial ante `429`.

**Retención**: el contenido original (título, cuerpo, autor) se elimina automáticamente a las 48 horas de
detectarse, o antes si el usuario lo borra manualmente o si el contenido se elimina en Reddit
(`purge_expired_reddit_content`, `sync_deleted_reddit_content`). Solo se conservan indefinidamente datos
operativos no identificativos: el ID de Reddit y la URL (para no volver a procesar la misma publicación), un
resumen no identificativo, la puntuación, la acción tomada y el resultado registrado manualmente por el usuario.

**Ausencia de publicación automática**: no existe, en ningún punto de la aplicación, un endpoint ni un botón que
publique un comentario en Reddit. Publicar es siempre un acto humano, manual, desde el propio Reddit.

**Ausencia de mensajes privados**: no se solicita el scope `privatemessages` ni se implementa ningún envío de
mensajes.

**Ausencia de votos**: no se solicita el scope `vote` ni se implementa ninguna votación automática.

**Uso de IA únicamente para clasificación y borradores**: cuando está activado (opcional, desactivado por
defecto), un proveedor de IA configurable solo recibe el título, cuerpo, subreddit e idioma estrictamente
necesarios para clasificar la conversación y sugerir un borrador — nunca el nombre de usuario del autor ni ningún
otro dato no necesario para esa clasificación.

**Ausencia de entrenamiento**: ningún contenido de Reddit se usa para entrenar ni afinar (fine-tune) ningún
modelo, en ningún punto del código.

**Aprobación humana antes de cualquier interacción**: toda respuesta se prepara como borrador editable; una
persona la revisa, la edita si quiere y la publica manualmente desde Reddit. La aplicación nunca actúa por sí
sola sobre una cuenta de Reddit.

**Medidas de privacidad**: separación estricta entre contenido temporal (purgado a las 48h) y datos operativos
agregados; aislamiento por cuenta mediante Row Level Security en la base de datos (ver `docs/data-model.md`);
tokens OAuth cifrados en reposo, nunca en texto plano; ningún secreto se devuelve nunca al frontend.

**Eliminación de contenido borrado en origen**: el job `sync_deleted_reddit_content` (desactivado mientras
`REDDIT_API_ENABLED=false`, implementado y listo para activarse) comprobará periódicamente si una publicación
sigue existiendo en Reddit y, si fue eliminada, la marcará como tal y se purgará su contenido igual que por
expiración temporal.

**Alcance de permisos solicitados (solo lectura)**: `identity`, `read`, `mysubreddits`. No se solicita `submit`,
`vote`, `privatemessages` ni ningún scope de moderación.

**User-Agent usado en todas las peticiones**: `radarin-conversation-radar/0.1 (internal tool; contact:
[completar email de contacto])` — configurable, nunca oculto.

---

*Completar los campos entre corchetes antes de enviar esta solicitud. Ver `docs/reddit-compliance.md` para el
detalle técnico de cómo se cumple cada uno de estos puntos en el código.*


## Estado del repositorio

Este borrador sigue siendo una solicitud, no una confirmación de aprobación. El código solicita únicamente scopes de
lectura y el modo automático permanece desactivado por defecto. La frecuencia prevista del fetch es cada 15 minutos,
limitada por watermark, paginación acotada y headers de rate limit; no se publica, vota ni envían DMs.
