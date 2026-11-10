"""Estado de un usuario virtual de los escenarios de comprobantes (importación, modificación masiva, crear).

En lugar de ejercicio/período/origen (pantalla Generar Asientos), estos escenarios necesitan los datos
maestros de la empresa: el período fiscal del mes de la fila, un proveedor y dos tipos de movimiento.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from holistor_stress.core.context import ContextoAsiento


@dataclass(frozen=True)
class Maestros:
    """Datos maestros resueltos por API con el token del propio usuario (sin ids fijos de un tenant)."""

    emp_codigo: int
    empresa_razon: str = ""
    periodo_fiscal_id: int | None = None
    periodo_fiscal_cod: str | None = None  # AAAAMM
    periodos: tuple[dict, ...] = ()  # períodos fiscales de la empresa (como los devuelve la API)
    proveedor_id: int | None = None
    proveedor_rz: str | None = None
    proveedor_tipo_doc: int | None = None
    proveedor_nro_doc: int | None = None
    proveedor_provincia_id: int | None = None
    proveedor_tipo_doc_abrev: str | None = None  # "CUIT", "DNI"… (para el CSV de la importación)
    mov_tipo_id_venta_neta: int | None = None
    mov_tipo_id_iva_cinco: int | None = None

    def periodo_id_por_cod(self, cod: str) -> int | None:
        """periodoFiscalId de la empresa para un código AAAAMM (None si no existe)."""
        for p in self.periodos:
            pcod = p.get("periodoFiscalCod") or p.get("codigo") or p.get("cod")
            if str(pcod).strip() == str(cod).strip():
                pid = p.get("periodoFiscalId") or p.get("id")
                return int(pid) if pid is not None else None
        return None


@dataclass
class ContextoComprobantes(ContextoAsiento):
    maestros: Maestros | None = None
    estado: dict = field(default_factory=dict)  # estado propio del escenario entre ciclos (origen, numeración…)

    @property
    def listo(self) -> bool:
        return bool(self.token and self.maestros)

    def limpiar_seleccion(self) -> None:
        self.maestros = None
