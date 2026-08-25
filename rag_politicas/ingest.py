import glob
import json
import os
import re

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from rag_politicas.chunking import chunk_documento
from rag_politicas.pdf_parser import extraer_texto_por_pagina

DIRECTORIO_POLITICAS = "materiales/politicas"
DIRECTORIO_DATA = os.path.join(os.path.dirname(__file__), "data")
RUTA_INDICE = os.path.join(DIRECTORIO_DATA, "index.faiss")
RUTA_CHUNKS = os.path.join(DIRECTORIO_DATA, "chunks.json")
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

PATRON_CODIGO = re.compile(r"Código\s+([A-Z]{2,6}-[A-Z]{2,6}-\d+)")


def extraer_codigo_politica(texto: str) -> str:
    match = PATRON_CODIGO.search(texto)
    if not match:
        raise ValueError("No se encontró el código de política en el subtítulo del documento.")
    return match.group(1)


def construir_chunks(directorio: str = DIRECTORIO_POLITICAS) -> tuple[list[dict], dict]:
    chunks = []
    titulos_documento = {}
    for ruta_pdf in sorted(glob.glob(os.path.join(directorio, "*.pdf"))):
        documento = os.path.basename(ruta_pdf)
        texto_completo = "\n".join(extraer_texto_por_pagina(ruta_pdf))
        codigo_politica = extraer_codigo_politica(texto_completo)
        titulos_documento[documento] = texto_completo.splitlines()[0].strip()
        for chunk in chunk_documento(texto_completo):
            chunks.append({
                "id": f"{codigo_politica}#{chunk['seccion']}",
                "documento": documento,
                "codigo_politica": codigo_politica,
                "seccion": chunk["seccion"],
                "titulo_seccion": chunk["titulo_seccion"],
                "texto": chunk["texto"],
            })
    return chunks, titulos_documento


def _texto_para_embedding(chunk: dict, titulos_documento: dict) -> str:
    """Antepone el título del documento y de la sección al cuerpo del chunk solo para
    el embedding, de forma que subsecciones sin contexto propio (p. ej. "3.1. La
    solicitud debe...") no pierdan su vínculo semántico con el documento al que
    pertenecen. El campo `texto` persistido en chunks.json no se modifica."""
    titulo_documento = titulos_documento[chunk["documento"]]
    return f"{titulo_documento}. {chunk['titulo_seccion']}\n{chunk['texto']}"


def construir_indice(chunks: list[dict], titulos_documento: dict, modelo: SentenceTransformer) -> faiss.Index:
    textos = [_texto_para_embedding(c, titulos_documento) for c in chunks]
    embeddings = modelo.encode(textos, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype="float32")
    indice = faiss.IndexFlatIP(embeddings.shape[1])
    indice.add(embeddings)
    return indice


def main():
    print(f"Leyendo PDF de {DIRECTORIO_POLITICAS}...")
    chunks, titulos_documento = construir_chunks()
    print(f"Se generaron {len(chunks)} chunks.")

    print(f"Cargando modelo de embeddings '{MODELO_EMBEDDINGS}'...")
    modelo = SentenceTransformer(MODELO_EMBEDDINGS)

    print("Generando embeddings y construyendo índice FAISS...")
    indice = construir_indice(chunks, titulos_documento, modelo)

    os.makedirs(DIRECTORIO_DATA, exist_ok=True)
    faiss.write_index(indice, RUTA_INDICE)
    with open(RUTA_CHUNKS, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"Índice escrito en {RUTA_INDICE}")
    print(f"Metadatos escritos en {RUTA_CHUNKS}")


if __name__ == "__main__":
    main()
