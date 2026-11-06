"""Conexión de SOLO CONSULTA a la base del tenant (autenticación de SQL Server, ODBC Driver 18).

Protecciones, aunque el usuario de la base tenga permisos de escritura:
1. `solo_select` rechaza cualquier sentencia que no sea un único SELECT (antes de enviarla).
2. La conexión se abre con ApplicationIntent=ReadOnly y sin autocommit; siempre termina en rollback.
3. La clave nunca aparece en mensajes de error ni en logs.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

from holistor_stress.config.settings import Settings

CAMPOS = ("SERVIDOR", "BASE", "USUARIO", "CLAVE")
_PROHIBIDAS = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke|deny|into|"
    r"backup|restore|dbcc|kill|shutdown|openrowset|opendatasource|xp_\w+|sp_\w+)\b",
    re.IGNORECASE,
)


class BDError(Exception):
    """Error de configuración, conexión o consulta (mensaje sin la clave)."""


@dataclass(frozen=True)
class ConfigBD:
    servidor: str
    base: str
    usuario: str
    clave: str = field(repr=False)
    driver: str = "ODBC Driver 18 for SQL Server"
    trust_server_certificate: bool = False
    timeout_s: int = 30

    @classmethod
    def desde(cls, settings: Settings, environ: Mapping[str, str] | None = None) -> ConfigBD:
        environ = os.environ if environ is None else environ
        cfg = settings.bd
        if not cfg.habilitada:
            raise BDError(f"la verificación en base está deshabilitada en environments/{settings.nombre}.yaml (bd)")
        valores = {k: (environ.get(cfg.prefijo_env + k) or "").strip() for k in CAMPOS}
        faltan = [cfg.prefijo_env + k for k, v in valores.items() if not v]
        if faltan:
            raise BDError(f"faltan variables de entorno (en .env): {', '.join(faltan)}")
        return cls(
            servidor=valores["SERVIDOR"],
            base=valores["BASE"],
            usuario=valores["USUARIO"],
            clave=valores["CLAVE"],
            driver=cfg.driver,
            trust_server_certificate=cfg.trust_server_certificate,
            timeout_s=cfg.timeout_s,
        )

    def cadena(self) -> str:
        def esc(v: str) -> str:
            return "{" + v.replace("}", "}}") + "}"

        return (
            f"DRIVER={{{self.driver}}};SERVER={esc(self.servidor)};DATABASE={esc(self.base)};"
            f"UID={esc(self.usuario)};PWD={esc(self.clave)};Encrypt=yes;"
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'};"
            f"ApplicationIntent=ReadOnly;Connection Timeout={self.timeout_s}"
        )

    def ocultar(self, texto: str) -> str:
        return texto.replace(self.clave, "***") if self.clave else texto


def _sin_comentarios_ni_textos(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)  # los literales no cuentan como palabras clave


def solo_select(sql: str) -> str:
    """Devuelve el SQL si es un único SELECT de lectura; si no, lanza BDError."""
    limpio = _sin_comentarios_ni_textos(sql).strip().rstrip(";").strip()
    if not re.match(r"(?is)^(with\b.+?\)\s*)?select\b", limpio):
        raise BDError("solo se permiten consultas SELECT")
    if ";" in limpio:
        raise BDError("solo se permite una sentencia por consulta")
    if m := _PROHIBIDAS.search(limpio):
        raise BDError(f"la consulta contiene una palabra no permitida: {m.group(0)}")
    return sql


class ConexionBD:
    def __init__(self, cfg: ConfigBD):
        self.cfg = cfg
        self._conn = None

    def __enter__(self) -> ConexionBD:
        try:
            import pyodbc
        except ImportError as e:
            raise BDError('falta pyodbc: pip install -e ".[bd]"') from e
        try:
            self._conn = pyodbc.connect(self.cfg.cadena(), autocommit=False, timeout=self.cfg.timeout_s)
        except pyodbc.Error as e:
            raise BDError(f"no se pudo conectar a {self.cfg.base}: {self.cfg.ocultar(str(e))[:400]}") from None
        return self

    def __exit__(self, *_exc) -> None:
        if self._conn is not None:
            try:
                self._conn.rollback()
            finally:
                self._conn.close()
                self._conn = None

    def consultar(self, sql: str) -> tuple[list[str], list[tuple]]:
        import pyodbc

        solo_select(sql)
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            columnas = [d[0] for d in cur.description or []]
            return columnas, [tuple(fila) for fila in cur.fetchall()]
        except pyodbc.Error as e:
            raise BDError(f"error en la consulta: {self.cfg.ocultar(str(e))[:400]}") from None
        finally:
            cur.close()
            self._conn.rollback()


@contextmanager
def conectar(settings: Settings, environ: Mapping[str, str] | None = None):
    with ConexionBD(ConfigBD.desde(settings, environ)) as conexion:
        yield conexion
