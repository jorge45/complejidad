import json
import os

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DIRECTORIO_DATA = os.path.join(os.path.dirname(__file__), "data")
RUTA_INDICE = os.path.join(DIRECTORIO_DATA, "index.faiss")
RUTA_CHUNKS = os.path.join(DIRECTORIO_DATA, "chunks.json")
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

# Calibrado con tests/casos_verificacion.py: separa los scores de las 5 preguntas
# con evidencia (0.63-0.84) de las preguntas fuera de corpus probadas (0.34-0.51).
# Nota: preguntas fuera de corpus con vocabulario que coincide fuerte con el corpus
# (p. ej. "atención al cliente" vs. "tiempos de atención" de SLA) pueden superar
# igualmente el umbral; es una limitación conocida del enfoque de umbral sobre
# embeddings de este modelo, documentada como riesgo en el spec.
UMBRAL_SIMILITUD_MINIMA = 0.55

_indice = None
_chunks = None
_modelo = None


def _cargar():
    global _indice, _chunks, _modelo
    if _indice is None:
        _indice = faiss.read_index(RUTA_INDICE)
    if _chunks is None:
        with open(RUTA_CHUNKS, encoding="utf-8") as f:
            _chunks = json.load(f)
    if _modelo is None:
        _modelo = SentenceTransformer(MODELO_EMBEDDINGS)
    return _indice, _chunks, _modelo


def buscar(pregunta: str, k: int = 4) -> list[dict]:
    """Devuelve los top-k chunks más relevantes para la pregunta, con su score de similitud coseno."""
    indice, chunks, modelo = _cargar()
    embedding = modelo.encode([pregunta], normalize_embeddings=True)
    embedding = np.asarray(embedding, dtype="float32")
    scores, indices = indice.search(embedding, k)
    resultados = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        resultado = dict(chunks[idx])
        resultado["score"] = float(score)
        resultados.append(resultado)
    return resultados


if __name__ == "__main__":
    import sys

    pregunta = sys.argv[1] if len(sys.argv) > 1 else "¿Con cuántos días de anticipación debo pedir vacaciones?"
    for r in buscar(pregunta):
        print(f"[{r['score']:.3f}] {r['documento']} §{r['seccion']} {r['titulo_seccion']}")
