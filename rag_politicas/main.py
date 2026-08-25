import logging

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag_politicas.generation import generar_respuesta
from rag_politicas.rate_limit import limitar_tasa
from rag_politicas.retrieval import UMBRAL_SIMILITUD_MINIMA, buscar

logger = logging.getLogger(__name__)

app = FastAPI(title="RAG Políticas Internas")

RESPUESTA_SIN_EVIDENCIA = "No tengo evidencia en las políticas para responder eso."


class ConsultaRequest(BaseModel):
    pregunta: str = Field(min_length=1, max_length=500)


class Fuente(BaseModel):
    documento: str
    seccion: str
    titulo_seccion: str


class ConsultaResponse(BaseModel):
    respuesta: str
    fuentes: list[Fuente]


@app.post("/consulta", response_model=ConsultaResponse, dependencies=[Depends(limitar_tasa)])
def consultar(request: ConsultaRequest) -> ConsultaResponse:
    chunks = buscar(request.pregunta)

    if not chunks or chunks[0]["score"] < UMBRAL_SIMILITUD_MINIMA:
        return ConsultaResponse(respuesta=RESPUESTA_SIN_EVIDENCIA, fuentes=[])

    try:
        respuesta = generar_respuesta(request.pregunta, chunks)
    except Exception:
        logger.exception("Fallo al generar la respuesta con el LLM")
        raise HTTPException(status_code=502, detail="No se pudo generar la respuesta en este momento.")

    fuentes = [
        Fuente(documento=c["documento"], seccion=c["seccion"], titulo_seccion=c["titulo_seccion"])
        for c in chunks
    ]
    return ConsultaResponse(respuesta=respuesta, fuentes=fuentes)
