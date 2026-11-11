"""Una fila de users.csv = un trabajo = un usuario virtual (mismo esquema que filas_performance.csv).

Módulos:
- GDC / SYJ: Generar Asiento → Crear Asiento.
- IMPO: importación de comprobantes de compra · MODIF: modificación masiva de cabecera ·
  CPBTE: crear comprobante de compra. Usan un único mes (AAAAMM) y cada locustfile toma solo
  las filas de su módulo.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from holistor_stress.data.periodo import RangoPeriodo, parsear_periodo

TIPOS_LOTE = ("COMPRAS", "VENTAS", "CERTIFICADOS_EMITIDOS", "CERTIFICADOS_RECIBIDOS")
MODULOS_ASIENTO = ("GDC", "SYJ")
MODULOS_COMPROBANTES = ("IMPO", "MODIF", "CPBTE")
Modulo = Literal["GDC", "SYJ", "IMPO", "MODIF", "CPBTE"]
TipoLote = Literal["COMPRAS", "VENTAS", "CERTIFICADOS_EMITIDOS", "CERTIFICADOS_RECIBIDOS"]


class FilaCarga(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1)
    activo: bool = True
    tenant_id: int = Field(alias="tenantId", gt=0)
    usuario: str = Field(min_length=1)
    clave: SecretStr | None = None
    modulo: Modulo
    empresa: int = Field(ge=0)
    periodo: str
    tipo_lote: TipoLote | None = Field(None, alias="tipoLote")
    reemplazar: bool | None = None
    plantilla: str | None = None
    ejercicio: int | None = None
    origen_asiento_id: int | None = Field(None, alias="origenAsientoId")
    comprobantes_a_incluir: str = Field("Todos", alias="comprobantesAIncluir")
    periodo_fiscal_id: int | None = Field(None, alias="periodoFiscalId")
    # gdc: Account/Authenticate del back de GDC (email + tenantId).
    # plataforma: IsTenantAvailable + TokenAuth/Authenticate de la plataforma SaaS (requiere `tenancy`).
    login: Literal["gdc", "plataforma"] = "gdc"
    tenancy: str | None = None  # nombre del tenant en la plataforma (GDCpruebasQA7)

    @model_validator(mode="before")
    @classmethod
    def _vacios_como_ausentes(cls, datos: Any) -> Any:
        # En el CSV una celda vacía significa "no informado": se usa el valor por defecto.
        if isinstance(datos, dict):
            return {k: v for k, v in datos.items() if not (isinstance(v, str) and v.strip() == "")}
        return datos

    @field_validator("modulo", "tipo_lote", mode="before")
    @classmethod
    def _mayusculas(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("login", mode="before")
    @classmethod
    def _minusculas(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("periodo")
    @classmethod
    def _periodo(cls, v: str) -> str:
        return str(parsear_periodo(v))

    @model_validator(mode="after")
    def _reglas_por_modulo(self) -> FilaCarga:
        if self.modulo == "GDC" and self.tipo_lote is None and self.origen_asiento_id is None:
            raise ValueError("GDC requiere 'tipoLote' (" + ", ".join(TIPOS_LOTE) + ") u 'origenAsientoId'")
        if self.modulo == "SYJ" and not self.plantilla:
            raise ValueError("SYJ requiere 'plantilla' (archivo JSON en la carpeta de plantillas SYJ)")
        if self.modulo in MODULOS_COMPROBANTES:
            r = self.rango
            if r.todos or r.desde != r.hasta:
                raise ValueError(
                    f"{self.modulo} trabaja sobre un único mes: 'periodo' debe ser AAAAMM (vino {self.periodo})"
                )
        if self.login == "plataforma" and not self.tenancy:
            raise ValueError("login=plataforma requiere 'tenancy' (nombre del tenant, por ejemplo GDCpruebasQA7)")
        return self

    @property
    def rango(self) -> RangoPeriodo:
        return parsear_periodo(self.periodo)

    @property
    def reemplazar_efectivo(self) -> bool | None:
        """GDC reemplaza por defecto; en SYJ vacío = respetar el Marca_Borrar del JSON."""
        if self.reemplazar is None and self.modulo == "GDC":
            return True
        return self.reemplazar

    @property
    def etiqueta(self) -> str:
        """Prefijo de logs y fallas, igual que en la colección: [GDC1 · E3064 · 202601-202606 · COMPRAS]."""
        quien = f"{self.usuario}@{self.tenancy}" if self.tenancy else self.usuario
        partes = [quien, f"E{self.empresa}", self.periodo, self.tipo_lote or self.modulo]
        return "[" + " · ".join(partes) + "]"

    def con_clave(self, clave: str) -> FilaCarga:
        return self.model_copy(update={"clave": SecretStr(clave)})
