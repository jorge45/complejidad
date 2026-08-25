"""Casos de verificación manual del RAG de políticas.

Ejecutar con: python -m tests.casos_verificacion
Valida la capa de retrieval + umbral (documento y sección citados, o "sin evidencia"),
sin invocar al LLM real (no requiere OPENAI_API_KEY).
"""
from rag_politicas.retrieval import UMBRAL_SIMILITUD_MINIMA, buscar

CASOS = [
    {
        "pregunta": "¿Con cuántos días de anticipación debo pedir vacaciones?",
        "documento_esperado": "POL-GTH-01_Vacaciones.pdf",
        "seccion_esperada": "3.1",
    },
    {
        "pregunta": "¿Cuántos días hábiles tengo para legalizar los gastos de un viaje de trabajo?",
        "documento_esperado": "POL-ADM-04_Viaticos.pdf",
        "seccion_esperada": "5.1",
    },
    {
        "pregunta": "¿En cuánto tiempo debo reportar a la mesa de ayuda la pérdida de un activo tecnológico?",
        "documento_esperado": "POL-TIC-02_Activos_Tecnologicos.pdf",
        "seccion_esperada": "5.1",
    },
    {
        "pregunta": "¿Cada cuánto tiempo se revisan los accesos otorgados a los colaboradores?",
        "documento_esperado": "POL-TIC-03_Gestion_de_Accesos.pdf",
        "seccion_esperada": "6",
    },
    {
        "pregunta": "¿Cuánto tiempo tengo para reabrir un ticket cerrado?",
        "documento_esperado": "POL-TIC-05_Gestion_de_Incidentes.pdf",
        "seccion_esperada": "6.1",
    },
    {
        "pregunta": "¿Cuál es la política de dividendos para los accionistas?",
        "documento_esperado": None,
        "seccion_esperada": None,
    },
]


def verificar_caso(caso: dict) -> bool:
    chunks = buscar(caso["pregunta"], k=4)
    mejor = chunks[0] if chunks else None
    hay_evidencia = mejor is not None and mejor["score"] >= UMBRAL_SIMILITUD_MINIMA

    if caso["documento_esperado"] is None:
        return not hay_evidencia

    return (
        hay_evidencia
        and mejor["documento"] == caso["documento_esperado"]
        and mejor["seccion"] == caso["seccion_esperada"]
    )


def main():
    total_ok = 0
    for caso in CASOS:
        ok = verificar_caso(caso)
        total_ok += ok
        estado = "OK" if ok else "FAIL"
        print(f"[{estado}] {caso['pregunta']}")
    print(f"\n{total_ok}/{len(CASOS)} casos pasaron.")
    if total_ok != len(CASOS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
