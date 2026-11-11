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
    # Escenarios de comprobantes (cada locustfile toma solo las filas de su módulo).
    impo: Modulo = Modulo(habilitado=True)  # importación de comprobantes de compra
    modif: Modulo = Modulo(habilitado=True)  # modificación masiva de cabecera
    cpbte: Modulo = Modulo(habilitado=True)  # crear comprobante de compra (lite y completo)

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


def _sin_barra(v: str) -> str:
    v = v.strip().rstrip("/")
    if not v.startswith(("http://", "https://")):
        raise ValueError(f"debe empezar con http:// o https:// (valor: {v!r})")
    return v


class Plataforma(_Base):
    """Hosts de la plataforma SaaS. Los usan las filas con `login=plataforma` y los escenarios que navegan.

    - `host_url`: login ABP (IsTenantAvailable + TokenAuth/Authenticate) y servicios de la plataforma.
    - `portal_url`: portal (Origin/Referer del login y páginas del portal).
    - `front_url`: front de Gestor de Comprobantes (stream de la importación y páginas del dashboard).
    """

    host_url: str
    portal_url: str
    front_url: str

    @field_validator("host_url", "portal_url", "front_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _sin_barra(v)


class Importacion(_Base):
    """Datos de prueba del escenario de importación (antes IMPO_* del .env). Sin valores fijos en el código:
    los de negocio son obligatorios si se corre el escenario."""

    origen_codigo: str  # código del origen de importación (PIC = Portal IVA); el id se busca en la API
    tipo_comprobante: str  # código ARCA del tipo de comprobante del CSV (11 = Factura C)
    moneda: str  # PES
    tipo_cambio: float = Field(gt=0)
    importe_min: float = Field(gt=0)
    importe_max: float = Field(gt=0)
    lote_n: int = Field(28, gt=0)  # comprobantes por archivo
    espera_empresa_libre_s: float = Field(600, gt=0)
    timeout_proceso_archivo_s: float = Field(3600, gt=0)
    timeout_job_s: float = Field(3600, gt=0)
    intervalo_sondeo_s: float = Field(5, gt=0)
    # GetListComprobantes rechaza limit > 100 ("limit must not be greater than 100").
    tam_pagina: int = Field(100, ge=1, le=100)
    plantilla: str = "data/plantillas/importacion/plantilla_importacion_compras_oficial.csv"

    @model_validator(mode="after")
    def _rango(self) -> Importacion:
        if self.importe_max < self.importe_min:
            raise ValueError(
                f"importe_max ({self.importe_max}) no puede ser menor que importe_min ({self.importe_min})"
            )
        return self


class Modificacion(_Base):
    """Escenario de modificación masiva de cabecera (antes MODIF_* del .env)."""

    # lote: `lote_n` comprobantes de una página al azar. todos: todo el período (ccpraIds=[] + isExclude=true).
    seleccion: Literal["lote", "todos"] = "lote"
    lote_n: int = Field(50, ge=1, le=100)
    # Cada ciclo usa el primer código DISTINTO del valor actual (siempre hay un cambio real).
    cond_fiscal: list[int] = Field(default_factory=lambda: [4, 1], min_length=1)
    provincia: list[int] = Field(default_factory=lambda: [18, 1], min_length=1)


class Maestros(_Base):
    """Datos maestros de los escenarios de comprobantes (empresa, período, proveedor, tipos de movimiento)."""

    # El primer usuario virtual de cada tenant/empresa/período hace los lookups y el resto los reutiliza
    # (antes CACHE_LOOKUPS): sin cache, con cientos de usuarios la rampa mide los lookups y no el escenario.
    cache: bool = True


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
    plataforma: Plataforma | None = None
    maestros: Maestros = Maestros()
    importacion: Importacion | None = None
    modificacion: Modificacion = Modificacion()

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
