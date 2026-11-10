"""Estado de un usuario virtual: su fila y lo que se fue resolviendo en la pantalla Generar Asientos."""

from __future__ import annotations

from dataclasses import dataclass

from holistor_stress.data.fila import FilaCarga


@dataclass(frozen=True)
class Ejercicio:
    codigo: int
    desde: str  # AAAA-MM-DD
    hasta: str  # AAAA-MM-DD


@dataclass(frozen=True)
class PeriodoResuelto:
    meses: tuple[str, ...]  # AAAAMM, solo los que existen en el ejercicio
    fecha_desde: str  # tal como la devuelve el servicio de períodos (se reenvía igual)
    fecha_hasta: str
    periodo_fiscal_id: int | None = None
    meses_fuera: tuple[str, ...] = ()  # pedidos en la fila pero fuera del ejercicio (no se generan)

    @property
    def primer_mes(self) -> str:
        return self.meses[0]


@dataclass(frozen=True)
class OrigenResuelto:
    origen_asiento_id: int
    tipo_lote: str | None
    tipo_comprobante_ids: tuple[int, ...]


@dataclass(frozen=True)
class Envio:
    """Un trabajo encolado en Crear Asiento."""

    request_id: str
    asientos: tuple[dict, ...]  # como los devolvió generar: empresa, ejercicio, idAsiento
    encolado_en: float  # time.perf_counter() al recibir el 202

    def claves(self) -> dict:
        """Body de jobs/estado y resultado-proceso: {asientos: [{empresa, ejercicio, idAsiento}]}."""
        return {
            "asientos": [
                {"empresa": a.get("empresa"), "ejercicio": a.get("ejercicio"), "idAsiento": id_asiento(a)}
                for a in self.asientos
            ]
        }


def id_asiento(asiento: dict) -> str:
    """El servidor no es consistente con el nombre del campo (idAsiento, IdAsiento, id, ID)."""
    for clave in ("idAsiento", "IdAsiento", "id", "ID"):
        if asiento.get(clave):
            return str(asiento[clave])
    return ""


@dataclass
class ContextoAsiento:
    fila: FilaCarga
    token: str | None = None
    ejercicio: Ejercicio | None = None
    periodo: PeriodoResuelto | None = None
    origen: OrigenResuelto | None = None
    registros_precheck: int | None = None  # None = todavía no se ejecutó el precheck
    # Solo con login=plataforma: header Abp.TenantId de cada request y userId del login.
    abp_tenant_id: int | None = None
    user_id: str | None = None

    @property
    def etiqueta(self) -> str:
        return self.fila.etiqueta

    @property
    def listo(self) -> bool:
        """Contexto completo para generar: sesión, empresa/ejercicio, período y (en GDC) origen."""
        base = bool(self.token and self.ejercicio and self.periodo)
        return base and (self.fila.modulo != "GDC" or self.origen is not None)

    def limpiar_seleccion(self) -> None:
        """Olvida lo resuelto en la pantalla (no la sesión ni el resultado del precheck)."""
        self.ejercicio = None
        self.periodo = None
        self.origen = None
