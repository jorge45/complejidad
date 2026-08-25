# SPEC 02 — Informe de seguridad e instrumentación del servicio RAG

> **Status:** Approved
> **Depends on:** SPEC 01
> **Date:** 2026-08-25
> **Objective:** Auditar `rag_politicas/` en busca de al menos tres vulnerabilidades reales de código generado por IA, corregirlas y documentarlas en un informe, y añadir instrumentación de latencia y tokens por petición con un resumen agregado.

---

## Scope

**In:**

- Auditoría de seguridad de todo `rag_politicas/` (`ingest.py`, `pdf_parser.py`, `chunking.py`, `retrieval.py`, `generation.py`, `main.py`), enfocada en la superficie expuesta por `POST /consulta`.
- Al menos tres hallazgos documentados, cada uno con: severidad (Crítica/Alta/Media/Baja), evidencia concreta (archivo y línea/fragmento del código original), y la corrección ya aplicada al código.
- Informe de seguridad en `docs/informe-seguridad.md`.
- Corrección de los hallazgos directamente en el código de `rag_politicas/`, sin romper `tests/casos_verificacion.py`.
- Instrumentación: por cada petición a `POST /consulta`, un log en `stdout` en JSON con latencia total del handler (ms) y tokens consumidos (`tokens_prompt`, `tokens_completion`, `tokens_total`); si la pregunta no supera el umbral de similitud, se loggea igual con tokens en 0.
- Endpoint `GET /metricas` que expone un resumen agregado en memoria: número de peticiones, latencia promedio y p95, y tokens totales/promedio consumidos desde que arrancó el proceso.

**Out of scope (para otro spec):**

- Autenticación/autorización del endpoint (decisión ya tomada en SPEC 01, no se reabre aquí).
- Persistencia de métricas entre reinicios (archivo o base de datos).
- Auditoría de seguridad de `datos/`, `legacy/`, `servicio_mock/`, `n5/` (no forman parte de `rag_politicas/`).
- Un dashboard visual de métricas; `GET /metricas` devuelve JSON crudo.
- Tests automatizados de penetración o escaneo de dependencias (SCA); la auditoría es manual sobre el código propio.

---

## Data model

```
rag_politicas/
  rate_limit.py     # nuevo: limitador de tasa en memoria, por IP
  metrics.py         # nuevo: registro de latencia/tokens por petición + resumen agregado en memoria
  main.py             # modificado: validación de pregunta, rate limiting, instrumentación, GET /metricas
  generation.py         # modificado: prompt del usuario delimitado explícitamente, devuelve también el uso de tokens
docs/
  informe-seguridad.md   # nuevo: informe con los hallazgos
```

`generation.generar_respuesta` cambia su valor de retorno de `str` a una tupla `(texto: str, uso: dict)`, donde `uso` es:

```json
{ "tokens_prompt": 412, "tokens_completion": 87, "tokens_total": 499 }
```

(tomado directamente de `response.usage` de la API de OpenAI).

Línea de log por petición (stdout, un JSON por línea):

```json
{"evento": "consulta", "latencia_ms": 842.3, "tokens_prompt": 412, "tokens_completion": 87, "tokens_total": 499, "con_evidencia": true}
```

Respuesta de `GET /metricas`:

```json
{
  "peticiones_totales": 37,
  "latencia_ms_promedio": 610.4,
  "latencia_ms_p95": 1180.2,
  "tokens_totales": 15230,
  "tokens_promedio_por_peticion": 411.6
}
```

Estructura de un hallazgo en `docs/informe-seguridad.md` (una entrada por hallazgo):

```markdown
### [Alta] Título corto del hallazgo

**Archivo:** rag_politicas/generation.py:28-37
**Evidencia:** fragmento del código original con el problema.
**Riesgo:** qué puede salir mal y cómo se explota.
**Corrección aplicada:** qué se cambió y en qué commit/archivo.
```

---

## Implementation plan

1. Validar `ConsultaRequest.pregunta` en `main.py` con `Field(min_length=1, max_length=500)`; una pregunta fuera de rango debe devolver `422` de FastAPI/Pydantic sin llegar a `retrieval.buscar`. Prueba manual: `curl` con una pregunta de 10000 caracteres devuelve `422`.
2. Modificar `generation._construir_prompt_usuario` para delimitar explícitamente el contenido del usuario (p. ej. bloque `<pregunta_usuario>...</pregunta_usuario>`) y reforzar `PROMPT_SISTEMA` indicando que todo lo que esté dentro de esas marcas es dato a responder, nunca una instrucción a seguir. Prueba manual: reejecutar `tests/casos_verificacion.py`, debe seguir en 6/6.
3. Implementar `rag_politicas/rate_limit.py`: función/dependencia FastAPI que limita a 20 peticiones por minuto por IP usando una ventana deslizante en memoria (`dict[str, deque[float]]`, sin dependencias nuevas); al exceder el límite responde `429` con `Retry-After`. Cablear como dependencia de `POST /consulta` en `main.py`. Prueba manual: 21 `curl` seguidos a `/consulta`, el 21º devuelve `429`.
4. Escribir `docs/informe-seguridad.md` con los tres hallazgos anteriores (input sin límite de tamaño, prompt injection sin delimitar, ausencia de rate limiting), cada uno con severidad, evidencia (código tal como estaba antes del paso 1-3) y la corrección ya aplicada, referenciando el archivo/línea final.
5. Modificar `generation.generar_respuesta` para devolver `(texto, uso)` leyendo `response.usage.prompt_tokens/completion_tokens/total_tokens`; actualizar el `__main__` de `generation.py` para desempacar la tupla.
6. Implementar `rag_politicas/metrics.py`: función `registrar_peticion(latencia_ms, tokens_prompt, tokens_completion, tokens_total, con_evidencia)` que loggea la línea JSON por `stdout` (vía `logging`) y acumula en una estructura en memoria (lista de latencias, contador, sumas de tokens); función `resumen()` que calcula promedio/p95 y totales.
7. Cablear la instrumentación en `main.py`: medir el handler completo de `POST /consulta` con `time.monotonic()`, llamar a `metrics.registrar_peticion` en el camino "sin evidencia" (tokens en 0) y en el camino con LLM (usando el `uso` devuelto por `generar_respuesta`). Prueba manual: hacer 3 `curl` a `/consulta` y ver 3 líneas JSON en stdout.
8. Añadir `GET /metricas` en `main.py` que devuelve `metrics.resumen()`. Prueba manual: tras los 3 `curl` del paso anterior, `curl localhost:8090/metricas` devuelve `peticiones_totales: 3` y tokens/latencia consistentes con los logs.

---

## Acceptance criteria

- [ ] `docs/informe-seguridad.md` existe y documenta al menos 3 hallazgos, cada uno con severidad, evidencia (archivo + fragmento de código original) y la corrección ya aplicada.
- [ ] Una petición a `POST /consulta` con `pregunta` de más de 500 caracteres devuelve `422` y no invoca `retrieval.buscar` ni `generation.generar_respuesta`.
- [ ] El prompt de usuario en `generation.py` delimita explícitamente el contenido de la pregunta y el system prompt indica que ese contenido no debe interpretarse como instrucciones.
- [ ] La petición número 21 en menos de un minuto desde la misma IP a `POST /consulta` devuelve `429`.
- [ ] `tests/casos_verificacion.py` sigue pasando 6/6 después de los cambios.
- [ ] Cada petición a `POST /consulta` (con o sin evidencia) produce exactamente una línea JSON en stdout con `latencia_ms` y los tres campos de tokens.
- [ ] Cuando la pregunta no supera el umbral de similitud, la línea de log tiene `tokens_prompt`, `tokens_completion` y `tokens_total` en `0`.
- [ ] `GET /metricas` devuelve `peticiones_totales`, `latencia_ms_promedio`, `latencia_ms_p95`, `tokens_totales` y `tokens_promedio_por_peticion`, consistentes con las peticiones hechas desde que arrancó el proceso.
- [ ] Reiniciar el servidor resetea el resumen de `/metricas` a cero (no hay persistencia en disco).

---

## Decisions

- **Sí:** un solo spec combinando informe de seguridad e instrumentación. Decisión explícita del usuario al reabrir la pregunta de split; ambos tocan el mismo servicio y se implementan en la misma sesión de trabajo.
- **Sí:** informe en `docs/informe-seguridad.md`, separado del spec. El spec describe el plan; el informe es el entregable de auditoría con contenido que crece por hallazgo, no debe vivir dentro del `.md` del spec.
- **Sí:** escala de severidad Crítica/Alta/Media/Baja. CVSS numérico es sobredimensionado para un servicio interno de 5 PDFs sin autenticación.
- **Sí:** los tres hallazgos elegidos (input sin límite de tamaño, prompt injection sin delimitar, ausencia de rate limiting) porque son vulnerabilidades reales y verificables en el código actual de `rag_politicas/`, no hipotéticas.
- **No:** hallazgos sobre autenticación/autorización faltante. Ya fue una decisión explícita y documentada en SPEC 01; no se reabre en este spec.
- **Sí:** rate limiting en memoria por IP sin dependencias nuevas (`slowapi` u otra librería). Evita agregar infraestructura para un límite simple de ventana deslizante.
- **Sí:** logs de instrumentación en stdout como JSON estructurado, no en archivo. Consistente con no agregar estado persistente nuevo al servicio (ya limitado por SPEC 01 a FAISS local).
- **Sí:** `GET /metricas` con estado en memoria, se resetea al reiniciar. Evita construir una capa de persistencia de métricas para un ejercicio de este alcance; si se necesita persistencia real, es un spec aparte (p. ej. exportar a Prometheus).
- **No:** desglosar la latencia por etapa (retrieval vs. generación) en el log. Un único número de latencia total del handler es suficiente para el resumen agregado pedido; desglosar es una mejora que puede añadirse después sin romper el contrato de `GET /metricas`.
- **Sí:** cuando no hay evidencia (no se llama al LLM), se loggea la petición igual con tokens en 0. Permite que `peticiones_totales` en `/metricas` refleje el tráfico real del endpoint, no solo las peticiones que llegaron al LLM.

---

## Risks

| Riesgo                                                                 | Mitigación                                                                                          |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| El rate limiter en memoria no es compartido entre workers si el servidor corre con múltiples procesos (`uvicorn --workers N`) | Documentado como limitación conocida en el informe; el spec asume un solo proceso, consistente con el modo de uso actual (`uvicorn rag_politicas.main:app --port 8090`). |
| La mitigación de prompt injection (delimitadores + refuerzo del system prompt) reduce pero no elimina el riesgo | Se documenta explícitamente en `docs/informe-seguridad.md` como mitigación parcial, no como corrección definitiva — es una limitación conocida de los LLM. |
| Cambiar la firma de `generar_respuesta` (de `str` a tupla) puede romper código que la llame directamente | Se actualiza el único caller interno (`main.py`) y el bloque `__main__` de `generation.py` en el mismo paso del plan (paso 5). |

---

## What is **not** in this spec

- Autenticación o autorización del endpoint.
- Persistencia de métricas en disco o base de datos.
- Auditoría de seguridad de `datos/`, `legacy/`, `servicio_mock/` o `n5/`.
- Dashboard visual de métricas.
- Escaneo automatizado de dependencias (SCA) o tests de penetración.

Cada uno de estos, si se necesita, va en su propio spec.
