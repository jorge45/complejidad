# RAG sobre políticas internas (PDF)

Servicio que ingiere los PDF de políticas internas de `materiales/politicas/`, los indexa por sección numerada y expone un endpoint HTTP que responde preguntas en lenguaje natural citando el documento y la sección de origen — o declara explícitamente que no hay evidencia en las políticas, sin inventar contenido.

Implementado según [`specs/01-rag-politicas.md`](specs/01-rag-politicas.md).

---

## Qué hace

1. **Ingesta** (`rag_politicas/ingest.py`): lee los 5 PDF de `materiales/politicas/`, extrae el texto con `pdfplumber`, detecta encabezados de sección/subsección numerados (`1.`, `3.1.`, ...) y genera un chunk por cada uno. Cada chunk se etiqueta con el código de la política (extraído del subtítulo del PDF, no del nombre de archivo), la sección y el título de sección.
2. **Embeddings e índice**: cada chunk se convierte en un vector con `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, local, sin llamadas de red) y se guarda en un índice vectorial FAISS (`rag_politicas/data/index.faiss`) junto con sus metadatos (`rag_politicas/data/chunks.json`).
3. **Endpoint `POST /consulta`** (FastAPI): recibe una pregunta, recupera los 4 chunks más relevantes por similitud coseno y:
   - Si el mejor chunk no supera el umbral mínimo de similitud, responde que no hay evidencia en las políticas — **sin llamar al LLM**.
   - Si lo supera, llama a OpenAI (`gpt-4o-mini`) para redactar una respuesta que cite explícitamente el documento y la sección de origen.

## Qué NO hace

- No ingiere `datos/`, `legacy/`, `servicio_mock/` ni `n5/` — son otras etapas de la prueba técnica, fuera de este spec.
- No tiene autenticación ni autorización en el endpoint.
- No tiene interfaz web ni cliente de chat — se consume por HTTP directo o por `/docs` (Swagger UI).
- No mantiene conversación multi-turno ni memoria de sesión: cada consulta es independiente.
- No actualiza el índice de forma incremental — cualquier cambio en los PDF requiere volver a correr `ingest.py` completo.
- No calcula métricas automatizadas de calidad de retrieval (precision/recall) — la verificación es el set de casos manual en `tests/casos_verificacion.py`.
- No decide por sí mismo (vía el LLM) si hay evidencia suficiente — esa decisión es puramente determinística (umbral de similitud), para evitar alucinaciones y llamadas innecesarias a la API.

## Estructura

```
rag_politicas/
  data/
    index.faiss          # índice vectorial FAISS
    chunks.json           # metadatos y texto de cada chunk
  ingest.py               # parseo PDF -> chunking -> embeddings -> índice
  pdf_parser.py            # extracción de texto con pdfplumber (limpia glifos "(cid:N)")
  chunking.py               # detección de secciones/subsecciones numeradas
  retrieval.py               # carga del índice, búsqueda top-k, score de similitud
  generation.py                # prompt + llamada a OpenAI (gpt-4o-mini)
  main.py                        # app FastAPI, POST /consulta
  requirements.txt
  .env.example
tests/
  casos_verificacion.py    # 5 preguntas (una por política) + 1 caso sin evidencia
```

---

## Instalación

Requiere Python 3.9+.

```bash
cd /Users/jorgeluis/Desktop/complejidad
python3 -m venv .venv
source .venv/bin/activate
pip install -r rag_politicas/requirements.txt
```

Configurar la API key de OpenAI:

```bash
cp rag_politicas/.env.example rag_politicas/.env
# editar rag_politicas/.env y poner OPENAI_API_KEY=sk-...
```

`rag_politicas/.env` está en `.gitignore` — nunca se versiona.

## Uso

### 1. Generar el índice (ingesta)

Debe correrse antes de levantar el servidor, y cada vez que cambien los PDF de `materiales/politicas/`:

```bash
python -m rag_politicas.ingest
```

Esto escribe `rag_politicas/data/index.faiss` y `rag_politicas/data/chunks.json`.

### 2. Levantar el servidor

```bash
uvicorn rag_politicas.main:app --port 8090
```

- Swagger UI: http://localhost:8090/docs
- Endpoint: `POST http://localhost:8090/consulta`

### 3. Consultar

```bash
curl -X POST localhost:8090/consulta \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Con cuántos días de anticipación debo pedir vacaciones?"}'
```

**Ejemplo de respuesta con evidencia:**

```json
{
  "respuesta": "De acuerdo con el documento POL-GTH-01_Vacaciones.pdf, sección 3.1, la solicitud de vacaciones debe radicarse con una anticipación mínima de quince (15) días calendario a la fecha de inicio del disfrute.",
  "fuentes": [
    { "documento": "POL-GTH-01_Vacaciones.pdf", "seccion": "3.1", "titulo_seccion": "La solicitud debe radicarse con una anticipación mínima de q..." },
    { "documento": "POL-GTH-01_Vacaciones.pdf", "seccion": "4.2", "titulo_seccion": "..." },
    { "documento": "POL-ADM-04_Viaticos.pdf", "seccion": "4.2", "titulo_seccion": "..." },
    { "documento": "POL-GTH-01_Vacaciones.pdf", "seccion": "4.1", "titulo_seccion": "..." }
  ]
}
```

**Ejemplo de pregunta fuera del corpus:**

```bash
curl -X POST localhost:8090/consulta \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Cuál es la política de dividendos para los accionistas?"}'
```

```json
{
  "respuesta": "No tengo evidencia en las políticas para responder eso.",
  "fuentes": []
}
```

Si la llamada al LLM falla (sin red, sin cuota, etc.), el endpoint devuelve `502` con un mensaje controlado en vez de una excepción cruda.

### 4. Correr los casos de verificación

Valida la capa de retrieval + umbral (5 preguntas, una por política, más 1 caso sin evidencia) sin necesidad de `OPENAI_API_KEY`:

```bash
python -m tests.casos_verificacion
```

Salida esperada: `6/6 casos pasaron.`

---

## Decisiones de diseño relevantes

- **Un chunk por sección/subsección numerada**, no ventanas de tamaño fijo — da citas exactas alineadas a la estructura real de las políticas.
- **Embeddings locales** (`sentence-transformers`), sin dependencia de red para esa parte del pipeline.
- **Generación con OpenAI** (`gpt-4o-mini`) — es la única llamada externa del sistema.
- **Umbral de similitud como mecanismo de "sin evidencia"**, evaluado antes de invocar al LLM: determinístico y barato. La constante `UMBRAL_SIMILITUD_MINIMA` vive en `rag_politicas/retrieval.py` y fue calibrada empíricamente con `tests/casos_verificacion.py` (actualmente `0.55`).
- Al indexar, el texto de cada chunk se antepone con el título del documento y de la sección **solo para el embedding** (no para lo que se cita al usuario), porque subsecciones cortas (p. ej. "La solicitud debe radicarse con...") pierden contexto semántico si se embeben aisladas.

## Limitación conocida

El umbral de similitud separa bien los casos probados en `tests/casos_verificacion.py`, pero preguntas fuera de corpus con vocabulario que coincide fuerte con el corpus (p. ej. "atención al cliente" vs. "tiempos de atención" de SLA de incidentes) pueden superar igual el umbral y no ser detectadas como "sin evidencia". Es una limitación inherente al enfoque de umbral sobre embeddings de un modelo pequeño, ya contemplada como riesgo en el spec.
