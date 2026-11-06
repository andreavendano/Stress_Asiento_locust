"""Modelo de la configuración de un ambiente (environments/<amb>.yaml).

`extra="forbid"` hace que un error de tipeo en el YAML (por ejemplo `intervalo` en vez de
`intervalo_s`) falle al cargar, en lugar de ignorarse en silencio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Datos(_Base):
    users_csv: str
    plantillas_syj: str = "data/plantillas/syj"
    clave_env_var: str | None = None
    # Comprobantes por empresa y mes (holistor-stress-volumen). Opcional: llena comprobantes_lote en trabajos.csv.
    volumen_csv: str | None = None


class Modulo(_Base):
    habilitado: bool


class Modulos(_Base):
    gdc: Modulo = Modulo(habilitado=True)
    syj: Modulo = Modulo(habilitado=False)

    def habilitado(self, modulo: str) -> bool:
        return getattr(self, modulo.lower()).habilitado


class Polling(_Base):
    intervalo_s: float = Field(3, gt=0)
    timeout_s: float = Field(600, gt=0)


class Flujo(_Base):
    contexto: Literal["una_vez", "cada_iteracion"] = "una_vez"
    precheck: Literal["off", "primer_mes", "completo"] = "primer_mes"
    seguimiento: Literal["progreso", "jobs_estado"] = "progreso"
    verificar_control: bool = True
    verificar_fechas: bool = True
    polling: Polling = Polling()
    relogin_401_max: int = Field(1, ge=0)
    # Fallas transitorias (5xx, timeout) seguidas al preparar el contexto antes de detener el usuario virtual.
    setup_reintentos_max: int = Field(3, ge=1)
    # periodoFiscalId si GetPeriodosFiscales no lo encuentra y la fila no trae uno. null = fallar (pregunta abierta 8).
    periodo_fiscal_id_defecto: int | None = 1


class WaitTime(_Base):
    min_s: float = Field(5, ge=0)
    max_s: float = Field(15, ge=0)

    @model_validator(mode="after")
    def _rango(self) -> WaitTime:
        if self.max_s < self.min_s:
            raise ValueError(f"max_s ({self.max_s}) no puede ser menor que min_s ({self.min_s})")
        return self


class BaseDatos(_Base):
    """Conexión de solo consulta a la base del tenant para verificar las corridas (verificacion.sql).

    Servidor, base, usuario y clave salen de variables de entorno <prefijo_env>SERVIDOR / BASE /
    USUARIO / CLAVE (en .env), nunca del YAML.
    """

    habilitada: bool = False
    prefijo_env: str = "HOLISTOR_QA_DB_"
    driver: str = "ODBC Driver 18 for SQL Server"
    trust_server_certificate: bool = False
    timeout_s: int = Field(30, gt=0)
    verificar_al_terminar: bool = True  # ejecuta la verificación al cerrar cada corrida con trabajos
    # tenantId → base de ese tenant (mismo servidor y usuario). Los tenants que no están usan la base del .env.
    bases_por_tenant: dict[int, str] = {}


class Thresholds(_Base):
    error_rate_max: float = Field(0.0, ge=0, le=1)
    p95_ms: dict[str, float] = {}
    e2e_p95_s: dict[str, float] = {}


class Settings(_Base):
    nombre: str
    base_url: str
    es_produccion: bool = False
    urls_produccion: list[str] = []
    idioma: str = "es"
    enviar_tenant_name: bool = False
    timeout_request_s: float = Field(60, gt=0)
    datos: Datos
    modulos: Modulos = Modulos()
    flujo: Flujo = Flujo()
    wait_time: WaitTime = WaitTime()
    thresholds: Thresholds = Thresholds()
    bd: BaseDatos = BaseDatos()

    # Carpeta raíz del proyecto; la completa el loader (no va en el YAML).
    raiz: Path

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"debe empezar con http:// o https:// (valor: {v!r})")
        return v

    def ruta(self, relativa: str | Path) -> Path:
        """Resuelve una ruta del YAML relativa a la raíz del proyecto."""
        p = Path(relativa)
        return p if p.is_absolute() else self.raiz / p
