import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

LIMITE_PETICIONES = 20
VENTANA_SEGUNDOS = 60.0

_peticiones_por_ip: dict[str, deque[float]] = defaultdict(deque)


def limitar_tasa(request: Request) -> None:
    ip = request.client.host if request.client else "desconocida"
    ahora = time.monotonic()
    ventana = _peticiones_por_ip[ip]

    while ventana and ahora - ventana[0] > VENTANA_SEGUNDOS:
        ventana.popleft()

    if len(ventana) >= LIMITE_PETICIONES:
        retry_after = max(0.0, VENTANA_SEGUNDOS - (ahora - ventana[0]))
        raise HTTPException(
            status_code=429,
            detail="Demasiadas peticiones. Intenta de nuevo más tarde.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    ventana.append(ahora)
