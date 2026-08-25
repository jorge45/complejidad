import re

import pdfplumber

PATRON_GLIFO_NO_RENDERIZABLE = re.compile(r"\(cid:\d+\)")


def _limpiar_texto(texto: str) -> str:
    """Quita glifos no renderizables (p. ej. viñetas) que pdfplumber deja como "(cid:N)"."""
    return PATRON_GLIFO_NO_RENDERIZABLE.sub("", texto)


def extraer_texto_por_pagina(ruta_pdf: str) -> list[str]:
    """Devuelve el texto de cada página del PDF, en orden."""
    paginas = []
    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            paginas.append(_limpiar_texto(texto))
    return paginas


if __name__ == "__main__":
    import sys

    ruta = sys.argv[1] if len(sys.argv) > 1 else "materiales/politicas/POL-GTH-01_Vacaciones.pdf"
    for i, texto in enumerate(extraer_texto_por_pagina(ruta), start=1):
        print(f"--- Página {i} ---")
        print(texto)
