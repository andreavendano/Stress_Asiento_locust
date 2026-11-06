"""Identificación de una corrida (para logs, reportes y trazabilidad en el servidor)."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    ambiente: str
    base_url: str
    inicio: str

    def como_dict(self) -> dict:
        return asdict(self)


def nueva_corrida(ambiente: str, base_url: str) -> RunInfo:
    ahora = datetime.now()
    run_id = f"{ambiente}-{ahora:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    return RunInfo(run_id=run_id, ambiente=ambiente, base_url=base_url, inicio=ahora.isoformat(timespec="seconds"))
