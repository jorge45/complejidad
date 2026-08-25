import json
import logging

logger = logging.getLogger(__name__)

_latencias_ms: list[float] = []
_peticiones_totales = 0
_tokens_prompt_total = 0
_tokens_completion_total = 0
_tokens_total = 0


def registrar_peticion(
    latencia_ms: float,
    tokens_prompt: int,
    tokens_completion: int,
    tokens_total: int,
    con_evidencia: bool,
) -> None:
    global _peticiones_totales, _tokens_prompt_total, _tokens_completion_total, _tokens_total

    logger.info(
        json.dumps(
            {
                "evento": "consulta",
                "latencia_ms": round(latencia_ms, 1),
                "tokens_prompt": tokens_prompt,
                "tokens_completion": tokens_completion,
                "tokens_total": tokens_total,
                "con_evidencia": con_evidencia,
            }
        )
    )

    _latencias_ms.append(latencia_ms)
    _peticiones_totales += 1
    _tokens_prompt_total += tokens_prompt
    _tokens_completion_total += tokens_completion
    _tokens_total += tokens_total


def _percentil(valores: list[float], percentil: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = int(round((percentil / 100) * (len(ordenados) - 1)))
    return ordenados[indice]


def resumen() -> dict:
    if _peticiones_totales == 0:
        return {
            "peticiones_totales": 0,
            "latencia_ms_promedio": 0.0,
            "latencia_ms_p95": 0.0,
            "tokens_totales": 0,
            "tokens_promedio_por_peticion": 0.0,
        }

    return {
        "peticiones_totales": _peticiones_totales,
        "latencia_ms_promedio": round(sum(_latencias_ms) / _peticiones_totales, 1),
        "latencia_ms_p95": round(_percentil(_latencias_ms, 95), 1),
        "tokens_totales": _tokens_total,
        "tokens_promedio_por_peticion": round(_tokens_total / _peticiones_totales, 1),
    }
