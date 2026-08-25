import re

PATRON_SECCION = re.compile(r"^[ \t]*(\d+(?:\.\d+)?)\.\s+(.+)$", re.MULTILINE)


def chunk_documento(texto: str) -> list[dict]:
    """Divide el texto completo de un documento en chunks por sección/subsección numerada.

    Cada chunk cubre desde su encabezado (p. ej. "3." o "3.1.") hasta el encabezado
    siguiente. Tolera espacio en blanco al inicio de línea (residuo de viñetas
    eliminadas en `pdf_parser`) para poder detectar subsecciones como "3.1.".
    """
    coincidencias = list(PATRON_SECCION.finditer(texto))
    chunks = []
    for i, match in enumerate(coincidencias):
        seccion = match.group(1)
        titulo_seccion = match.group(2).strip()
        inicio = match.start()
        fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
        cuerpo = texto[inicio:fin].strip()
        chunks.append({
            "seccion": seccion,
            "titulo_seccion": titulo_seccion,
            "texto": cuerpo,
        })
    return chunks


if __name__ == "__main__":
    import sys

    from rag_politicas.pdf_parser import extraer_texto_por_pagina

    ruta = sys.argv[1] if len(sys.argv) > 1 else "materiales/politicas/POL-GTH-01_Vacaciones.pdf"
    texto_completo = "\n".join(extraer_texto_por_pagina(ruta))
    chunks = chunk_documento(texto_completo)
    print(f"Total de chunks: {len(chunks)}")
    for c in chunks:
        print(f"- Sección {c['seccion']}: {c['titulo_seccion']}")
