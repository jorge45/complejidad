# SPEC 01 — RAG sobre políticas internas en PDF

> **Status:** Implementado
> **Depends on:** ninguno
> **Date:** 2026-08-25
> **Objective:** Construir un servicio que ingiera los PDF de `materiales/politicas/`, los indexe por sección y exponga un endpoint que responda preguntas citando el documento y la sección de origen, o declare que no hay evidencia.

---

## Scope

**In:**

- Script de ingesta que lee los 5 PDF de `materiales/politicas/`, extrae texto con `pdfplumber`, detecta secciones/subsecciones numeradas (`1.`, `3.1`, ...) y genera un chunk por sección.
- Generación de embeddings locales con `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) para cada chunk.
- Índice vectorial FAISS persistido en disco junto con un JSON de metadatos (documento, código de política, título de sección, texto del chunk).
- Endpoint HTTP `POST /consulta` (FastAPI) que recibe una pregunta en lenguaje natural, recupera los chunks más relevantes, y usa un LLM (OpenAI) para redactar una respuesta que cite documento y sección.
- Umbral de similitud mínima: si el mejor chunk recuperado no lo supera, el endpoint responde que no hay evidencia en las políticas, sin llamar al LLM.
- Manejo de `OPENAI_API_KEY` vía archivo `.env` (no versionado) con `python-dotenv`.
- Set de preguntas de verificación (`tests/casos_verificacion.py` o `.json`) que cubre las 5 políticas más un caso fuera del corpus.

**Out of scope (para otro spec):**

- Ingesta de `datos/tickets_historicos.csv`, `datos/esquema.sql`, `legacy/legacy_module.py`, `servicio_mock/` o `n5/` — pertenecen a otras etapas de la prueba técnica.
- Autenticación/autorización del endpoint.
- Interfaz web o cliente de chat; el endpoint se consume vía HTTP directo o Swagger UI (`/docs`).
- Conversación multi-turno o memoria de sesión: cada consulta es independiente.
- Actualización incremental del índice ante cambios de los PDF (se asume reingesta completa vía el script).
- Métricas de evaluación automatizadas (precision/recall del retrieval); la verificación es el set de casos manual descrito arriba.

---

## Data model

```
rag_politicas/
  data/
    index.faiss          # índice vectorial FAISS
    chunks.json           # metadatos y texto de cada chunk, alineado por posición con index.faiss
  ingest.py               # parseo PDF -> chunking -> embeddings -> construcción del índice
  pdf_parser.py            # extracción de texto y detección de secciones con pdfplumber
  chunking.py               # un chunk por sección/subsección numerada
  retrieval.py               # carga del índice, búsqueda top-k, cálculo de score de similitud
  generation.py                # llamada al LLM (OpenAI) con los chunks recuperados
  main.py                        # app FastAPI, define POST /consulta
  requirements.txt
  .env.example
tests/
  casos_verificacion.py    # o .json, ~5-8 preguntas con respuesta/sección esperada + 1 caso sin evidencia
```

Estructura de un chunk en `chunks.json`:

```json
{
  "id": "POL-GTH-01#3.1",
  "documento": "POL-GTH-01_Vacaciones.pdf",
  "codigo_politica": "POL-GTH-01",
  "seccion": "3.1",
  "titulo_seccion": "Solicitud y aprobación",
  "texto": "La solicitud debe radicarse con una anticipación mínima de quince (15) días calendario..."
}
```

Contrato del endpoint `POST /consulta`:

```json
// request
{ "pregunta": "¿Con cuánta anticipación debo pedir vacaciones?" }

// response (con evidencia)
{
  "respuesta": "Debes radicar la solicitud con al menos 15 días calendario de anticipación (POL-GTH-01, sección 3.1).",
  "fuentes": [
    { "documento": "POL-GTH-01_Vacaciones.pdf", "seccion": "3.1", "titulo_seccion": "Solicitud y aprobación" }
  ]
}

// response (sin evidencia)
{
  "respuesta": "No tengo evidencia en las políticas para responder eso.",
  "fuentes": []
}
```

Convenciones:

- El `id` de cada chunk es `{codigo_politica}#{seccion}`.
- `codigo_politica` se extrae del subtítulo del PDF (ej. "Código POL-GTH-01"), no del nombre de archivo, para tolerar discrepancias.
- Top-k de recuperación: 4 chunks.
- Umbral de similitud coseno mínimo: 0.35 (documentado como constante en `retrieval.py`, ajustable).
- Modelo de generación: `gpt-4o-mini`.

---

## Implementation plan

1. Crear `rag_politicas/` con `requirements.txt` (pdfplumber, sentence-transformers, faiss-cpu, fastapi, uvicorn, openai, python-dotenv, pydantic) y `.env.example` con `OPENAI_API_KEY=`.
2. Implementar `pdf_parser.py`: función que recibe la ruta de un PDF y devuelve el texto por página en orden, usando `pdfplumber`. Prueba manual: correrlo sobre `POL-GTH-01_Vacaciones.pdf` e imprimir el texto extraído.
3. Implementar `chunking.py`: función que recibe el texto completo de un documento y devuelve una lista de chunks `{seccion, titulo_seccion, texto}`, usando una expresión regular que detecta encabezados de sección (`^\d+\.\s` y `^\d+\.\d+\.\s`). Prueba manual: correrlo sobre el texto de `POL-GTH-01` y verificar que produce 8 chunks (secciones 1 a 8).
4. Implementar `ingest.py`: recorre los 5 PDF de `materiales/politicas/`, aplica `pdf_parser` + `chunking`, genera embeddings con `sentence-transformers`, construye el índice FAISS y escribe `data/index.faiss` + `data/chunks.json`. Ejecutable como `python -m rag_politicas.ingest`. Prueba manual: correrlo y confirmar que ambos archivos se crean con >0 chunks.
5. Implementar `retrieval.py`: carga `index.faiss` y `chunks.json`, expone una función `buscar(pregunta: str, k: int = 4)` que devuelve los chunks top-k con su score de similitud coseno.
6. Implementar `generation.py`: función `generar_respuesta(pregunta, chunks)` que arma un prompt con los chunks recuperados (texto + documento + sección) y llama a la API de OpenAI (`gpt-4o-mini`) pidiendo una respuesta que cite documento y sección explícitamente.
7. Implementar `main.py`: app FastAPI con `POST /consulta`. Si el mejor score de `retrieval.buscar` está por debajo de 0.35, responde el mensaje de "sin evidencia" sin llamar a `generation`. Si lo supera, llama a `generation.generar_respuesta` y arma la respuesta con `fuentes`. Ejecutable con `uvicorn rag_politicas.main:app --port 8090`. Prueba manual: `curl -X POST localhost:8090/consulta -d '{"pregunta": "..."}"`.
8. Escribir `tests/casos_verificacion.py` con preguntas que cubran las 5 políticas y un caso fuera de corpus (ver Acceptance criteria).

---

## Acceptance criteria

- [x] `python -m rag_politicas.ingest` corre sin errores y genera `rag_politicas/data/index.faiss` y `rag_politicas/data/chunks.json`.
- [x] `chunks.json` contiene al menos un chunk por cada una de las 5 políticas, cada uno con `documento`, `codigo_politica`, `seccion`, `titulo_seccion` y `texto` no vacíos.
- [x] Levantar `uvicorn rag_politicas.main:app --port 8090` expone `POST /consulta` y `GET /docs`.
- [x] Una pregunta cuya respuesta está en el corpus (ej. "¿Con cuántos días de anticipación debo pedir vacaciones?") devuelve una `respuesta` que menciona el valor correcto (15 días) y `fuentes` con `documento: POL-GTH-01_Vacaciones.pdf` y `seccion: 3.1`.
- [x] Una pregunta fuera del corpus (tema no cubierto por ninguna de las 5 políticas) devuelve `fuentes: []` y una `respuesta` que indica explícitamente que no hay evidencia, sin inventar contenido.
- [x] Los 5-8 casos de `tests/casos_verificacion.py` pasan: cada uno con evidencia cita el documento y sección esperados; el caso sin evidencia no cita ninguna fuente.
- [x] `.env` no está versionado (aparece en `.gitignore`) y `.env.example` documenta `OPENAI_API_KEY` vacía.

---

## Decisions

- **Sí:** un chunk por sección/subsección numerada. Las políticas ya tienen estructura numerada consistente y el endpoint debe citar "sección de origen" — alinear el chunk a la sección real da citas exactas sin heurísticas de solapamiento.
- **No:** ventanas de tamaño fijo con overlap. Rompería los límites de sección y produciría citas aproximadas o ambiguas.
- **Sí:** embeddings locales con `sentence-transformers` multilingüe. Sin dependencia de red ni API key para esta etapa del pipeline, coherente con que los datos (aunque sintéticos) no deben salir de la máquina.
- **Sí:** generación de la respuesta final con OpenAI (`gpt-4o-mini`). El enunciado pide que el endpoint "responda" citando, no solo que liste fragmentos; se decidió no usar Anthropic aquí porque el usuario indicó OpenAI explícitamente para esta pieza.
- **Sí:** umbral de similitud mínima (0.35) como mecanismo de "sin evidencia", evaluado antes de invocar al LLM. Es determinístico, barato (no gasta tokens de generación) y evita que el LLM alucine una respuesta cuando el retrieval no encontró nada relevante.
- **No:** dejar que el LLM decida por sí solo si hay evidencia. Es menos predecible y no evita la llamada innecesaria a la API cuando el retrieval ya sabe que no hay match.
- **Sí:** FAISS local persistido en disco, reconstruido solo por el script `ingest.py`. Con 5 PDFs no se justifica un servidor de base vectorial; reconstruir en cada arranque del servidor sería trabajo repetido innecesario.
- **No:** reconstrucción automática del índice al arrancar el servidor. Separa claramente la fase de ingesta (offline, se corre cuando cambian los PDF) de la fase de servir consultas (rápida, sin recomputar embeddings).
- **Sí:** `pdfplumber` sobre `pypdf`. La política de Vacaciones incluye una tabla (sección 7) y `pdfplumber` preserva mejor el orden de texto alrededor de tablas, reduciendo el riesgo de romper la detección de encabezados de sección.
- **Sí:** código de política (`POL-GTH-01`, etc.) extraído del subtítulo del PDF, no del nombre de archivo. Es la fuente canónica del código y evita depender de que el nombre de archivo no cambie.

---

## Risks

| Riesgo                                                                 | Mitigación                                                                                          |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| El regex de detección de secciones falla si un PDF usa un formato distinto de numeración | Cada política se revisa manualmente tras la ingesta (paso 4 del plan); si falla, se ajusta el patrón por documento antes de continuar. |
| La API de OpenAI no está disponible o falla (sin red, cuota agotada)     | El endpoint debe devolver un error controlado (5xx con mensaje claro) en vez de una excepción cruda; no hay retry automático en el alcance de este spec. |
| El umbral de similitud (0.35) es demasiado alto o bajo para este corpus  | Se documenta como constante ajustable en `retrieval.py`; se calibra manualmente con el set de verificación durante el paso 8. |

---

## What is **not** in this spec

- Ingesta de `datos/`, `legacy/`, `servicio_mock/` ni `n5/` (otras etapas de la prueba técnica).
- Autenticación del endpoint.
- Interfaz de usuario o cliente de chat.
- Conversación multi-turno.
- Actualización incremental del índice.
- Métricas automatizadas de calidad de retrieval (solo el set de verificación manual).

Cada uno de estos, si se necesita, va en su propio spec.
