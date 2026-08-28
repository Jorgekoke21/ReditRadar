# Modo Manual

El modo manual es el corazón de la aplicación mientras la integración con la API de Reddit está desactivada
(estado por defecto). Funciona **sin ninguna llamada externa** — ni a Reddit, ni a un proveedor de IA, ni a un
proveedor de email.

## Cómo funciona

1. El usuario pega los datos de una publicación en `/manual-import`: URL (opcional), subreddit, título, texto,
   número de comentarios, fecha aproximada e idioma.
2. `POST /api/conversations/manual` crea la conversación con `source_mode=manual` y, en el mismo request:
   - la deduplica (ver `docs/data-model.md`) — si ya existe, devuelve la existente sin crear una fila nueva;
   - le asigna `expires_at = ahora + 48h` (retención del contenido original);
   - la analiza inmediatamente con `RulesConversationAnalyzer` (o el analizador de IA, si está activo);
   - calcula su puntuación y genera los borradores de respuesta si la puntuación lo justifica.
3. El usuario ve el resultado al instante — no hace falta esperar a ningún job programado.

## Diferencia clave frente al modo Reddit API

El filtro inicial (`app/services/initial_filter.py`, sección 10 del encargo) comprueba, entre otras cosas, que la
conversación pertenezca a una "comunidad vigilada". Para conversaciones `reddit_api`, esto exige que exista una fila
en `communities` con `is_active=true` para ese subreddit — tiene sentido, porque solo se debería haber llegado ahí
vigilando ese subreddit a propósito.

Para conversaciones `manual` y `demo`, esta comprobación **se omite salvo que el usuario haya registrado
explícitamente esa comunidad y la haya desactivado** (`app/services/jobs.py::_analyze_one`). Es una decisión de
diseño deliberada: el encargo exige que el modo manual funcione "sin ninguna API externa" y sin configuración
previa — obligar a registrar antes cada subreddit habría roto justo ese requisito.

## Importación CSV

`POST /api/conversations/import` acepta un archivo con cabeceras:

```
url,subreddit,title,body,num_comments,language,published_at
```

- `url`, `body`, `num_comments`, `language`, `published_at` son opcionales.
- Cada fila pasa por el mismo pipeline que la importación manual (dedupe + análisis inmediato).
- El resultado (`CSVImportResult`) reporta `imported`, `duplicates` y una lista de `errors` con el número de fila y
  el motivo — una fila mal formada no aborta el resto del archivo (importación parcial con avisos, tal como pide
  el encargo en la sección de estados del sistema).

## Límites conocidos

- No hay una plantilla de CSV descargable en la interfaz (solo se documentan las columnas esperadas en la propia
  pantalla). Añadir un botón de descarga de plantilla sería una mejora sencilla si se necesita.
- El campo `fecha aproximada` en el formulario web solo acepta un día (sin hora); quien necesite mayor precisión
  puede usar `published_at` con hora completa vía CSV.
