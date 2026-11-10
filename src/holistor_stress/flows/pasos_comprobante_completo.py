"""Crear comprobante de compra, flujo COMPLETO (antes tasks/gdc.py, 113 pasos de la grabación de Blazemeter).

Reproduce la navegación del navegador (portal, dashboard, banners, suscripciones, lookups de la pantalla) y en
el medio crea el comprobante (paso 103) y abre su detalle (108/109). Los pasos de navegación están en la tabla
`ANTES` / `DESPUES_GRILLA` / `FINAL`, generada a partir del archivo original: mismos métodos, URLs, nombres,
headers y bodies. Solo cambió de dónde salen los valores dinámicos (`{emp}`, `{periodo_id}`…: datos maestros).

Hosts: `{plataforma}` = plataforma.host_url · `{portal}` = plataforma.portal_url · `{front}` =
plataforma.front_url · `{back}` = base_url (back de Gestor de Comprobantes). Requiere `login=plataforma`.

Los pasos de navegación no cortan el flujo (como en el navegador): solo se marcan como falla si responden
>= 400. El ciclo ("CPBTE 00 …") falla si el comprobante no se crea o no se puede leer su detalle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ruff: noqa: E501  (tabla generada: headers y URLs de la grabación, sin partir)


@dataclass(frozen=True)
class Paso:
    nro: int
    metodo: str
    url: str  # plantilla con {plataforma}, {portal}, {front}, {back} y los valores dinámicos
    nombre: str  # nombre en Locust (puede llevar {emp})
    headers: dict
    cuerpo: Callable[[dict], Any] | None = None


# Pasos 1 a 102: navegación hasta la pantalla "Nuevo comprobante de compra".
ANTES: list[Paso] = [
    # Paso 1 (antes Paso 2): POST /Azure/CheckTenant
    Paso(1, 'POST', '{plataforma}/api/services/app/Azure/CheckTenant', '/api/services/app/Azure/CheckTenant', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 2 (antes Paso 3): GET portal (EnvConfig.get_portal_url())
    Paso(2, 'GET', '{portal}/', '/', {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'}),
    # Paso 3 (antes Paso 4): GET appconfig.production.json
    Paso(3, 'GET', '{portal}/assets/appconfig.production.json?d=1790955614059', '/assets/appconfig.production.json', {'Content-type': 'application/json', 'Accept': '*/*'}),
    # Paso 4 (antes Paso 5): GET /AbpUserConfiguration/GetAll
    Paso(4, 'GET', '{plataforma}/AbpUserConfiguration/GetAll?d=1790955614223', '/AbpUserConfiguration/GetAll', {'.AspNetCore.Culture': 'c=null|uic=null', 'Content-type': 'application/json', 'Accept': '*/*'}),
    # Paso 5 (antes Paso 6): GET /Session/GetCurrentLoginInformations
    Paso(5, 'GET', '{plataforma}/api/services/app/Session/GetCurrentLoginInformations', '/api/services/app/Session/GetCurrentLoginInformations', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 7: GET Profile/GetProfilePicture
    Paso(7, 'GET', '{plataforma}/api/services/app/Profile/GetProfilePicture', '/api/services/app/Profile/GetProfilePicture', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 8: GET Aplicaciones/GetAllWithoutPaged
    Paso(8, 'GET', '{plataforma}/api/services/app/Aplicaciones/GetAllWithoutPaged', '/api/services/app/Aplicaciones/GetAllWithoutPaged', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 9: GET Banner/GetActiveBanners
    Paso(9, 'GET', '{plataforma}/api/services/app/Banner/GetActiveBanners', '/api/services/app/Banner/GetActiveBanners', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 10: GET UserLink/GetRecentlyUsedLinkedUsers
    Paso(10, 'GET', '{plataforma}/api/services/app/UserLink/GetRecentlyUsedLinkedUsers', '/api/services/app/UserLink/GetRecentlyUsedLinkedUsers', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 11: GET AtencionRemota/GetRemoteAssistanceOrder
    Paso(11, 'GET', '{plataforma}/api/services/app/AtencionRemota/GetRemoteAssistanceOrder?userId={user_id}', '/api/services/app/AtencionRemota/GetRemoteAssistanceOrder', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 12: GET UserLink/GetLinkedUsers
    Paso(12, 'GET', '{plataforma}/api/services/app/UserLink/GetLinkedUsers?MaxResultCount=10&SkipCount=0', '/api/services/app/UserLink/GetLinkedUsers', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 13: GET Notification/GetUserNotifications top 3
    Paso(13, 'GET', '{plataforma}/api/services/app/Notification/GetUserNotifications?MaxResultCount=3&SkipCount=0', '/api/services/app/Notification/GetUserNotifications', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 14: GET Notification/GetUserNotifications State=0
    Paso(14, 'GET', '{plataforma}/api/services/app/Notification/GetUserNotifications?State=0', '/api/services/app/Notification/GetUserNotifications', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 15: POST Suscripciones/EstadoAplicacion GC
    Paso(15, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=GC', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 16: POST Suscripciones/EstadoAplicacion AGE
    Paso(16, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=AGE', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 17: POST Suscripciones/EstadoAplicacion SYJ
    Paso(17, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=SYJ', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 18: POST Suscripciones/EstadoAplicacion CTB
    Paso(18, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=CTB', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 19: POST Suscripciones/EstadoAplicacion GDC
    Paso(19, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=GDC', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 20: POST Suscripciones/EstadoAplicacion GDC 2
    Paso(20, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=GDC', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 21: POST Suscripciones/EstadoAplicacion GC 2
    Paso(21, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=GC', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 22: POST Suscripciones/EstadoAplicacion SYJ 2
    Paso(22, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=SYJ', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 23: POST Suscripciones/EstadoAplicacion CTB 2
    Paso(23, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=CTB', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 24: POST Suscripciones/EstadoAplicacion AGE 2
    Paso(24, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=AGE', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 25: POST Suscripciones/EstadoAplicacion PDF
    Paso(25, 'POST', '{plataforma}/api/services/app/Suscripciones/EstadoAplicacion?appFeatureNamePlataforma=PDF', '/api/services/app/Suscripciones/EstadoAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 26: POST AtencionRemota/HasAssistanceOrderActive
    Paso(26, 'POST', '{plataforma}/api/services/app/AtencionRemota/HasAssistanceOrderActive?userId={user_id}', '/api/services/app/AtencionRemota/HasAssistanceOrderActive', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 27: POST SolicitudAccesoComprobantesGE/ExisteAccesoVigente
    Paso(27, 'POST', '{plataforma}/api/services/app/SolicitudAccesoComprobantesGE/ExisteAccesoVigenteComprobantesGETenantLogueado', '/api/services/app/SolicitudAccesoComprobantesGE/ExisteAccesoVigenteComprobantesGETenantLogueado', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 28: POST AccesoBd/HasAssistanceOrderActive
    Paso(28, 'POST', '{plataforma}/api/services/app/AccesoBd/HasAssistanceOrderActive?userId={user_id}', '/api/services/app/AccesoBd/HasAssistanceOrderActive', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 29: POST SolicitudAccesoComprobantesGE/HasOrderActive  (tenantId DINAMICO del user logueado)
    Paso(29, 'POST', '{plataforma}/api/services/app/SolicitudAccesoComprobantesGE/HasOrderActive?tenantId={tenant_id}', '/api/services/app/SolicitudAccesoComprobantesGE/HasOrderActive', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 30: GET Aplicaciones/GetAppServiceBaseUrl idAplicacion=5
    Paso(30, 'GET', '{plataforma}/api/services/app/Aplicaciones/GetAppServiceBaseUrl?idAplicacion=5', '/api/services/app/Aplicaciones/GetAppServiceBaseUrl', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 31: POST Suscripciones/InitAplicacion GDC
    Paso(31, 'POST', '{plataforma}/api/services/app/Suscripciones/InitAplicacion?appFeatureNamePlataforma=GDC', '/api/services/app/Suscripciones/InitAplicacion', {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Sat, 01 Jan 2000 00:00:00 GMT', 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/plain'}),
    # Paso 32: GET gestor-comprobantes-front /dashboard?token=...
    Paso(32, 'GET', '{front}/dashboard?token={token}', '/dashboard', {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'}),
    # Paso 33: GET gestor-comprobantes-front /dashboard?_rsc=...
    Paso(33, 'GET', '{front}/dashboard?_rsc=hi3jv', '/dashboard', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 34: GET GdC Back Security/GetValidarToken
    Paso(34, 'GET', '{back}/api/services/app/Security/GetValidarToken', '/api/services/app/Security/GetValidarToken', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 35: GET GdC Back Session/GetCurrentLoginInformations
    Paso(35, 'GET', '{back}/api/services/app/Session/GetCurrentLoginInformations', '/api/services/app/Session/GetCurrentLoginInformations', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 36: GET gestor-comprobantes-front /dashboard
    Paso(36, 'GET', '{front}/dashboard', '/dashboard', {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'}),
    # Paso 37: POST GdC Back Empresas/GetEmpresasByTenant
    Paso(37, 'POST', '{back}/api/services/app/Empresas/GetEmpresasByTenant', '/api/services/app/Empresas/GetEmpresasByTenant', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'filter': {'appModCod': 'GDC', 'activo': True}, 'search': ''}),
    # Paso 38: GET GdC Back Security/GetValidarToken 2
    Paso(38, 'GET', '{back}/api/services/app/Security/GetValidarToken', '/api/services/app/Security/GetValidarToken', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 39: GET GdC Back Security/GetSecurity
    Paso(39, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 40: GET GdC Back GdcConfig/GetLinks GDCLINKAYUDA
    Paso(40, 'GET', '{back}/api/services/app/GdcConfig/GetLinks?codigo=GDCLINKAYUDA', '/api/services/app/GdcConfig/GetLinks', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 41: GET GdC Back GdcConfig/GetLinks GDCLINKNOVEDADES
    Paso(41, 'GET', '{back}/api/services/app/GdcConfig/GetLinks?codigo=GDCLINKNOVEDADES', '/api/services/app/GdcConfig/GetLinks', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 42: POST GdC Back GdcImpoOrigen/GetListForImport Venta
    Paso(42, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'Activo': True, 'OrigenImpo': False}}),
    # Paso 43: POST GdC Back GdcImpoOrigen/GetListForImport Compra
    Paso(43, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'Activo': True, 'OrigenImpo': False}}),
    # Paso 44: GET GdC Back GdcPeriodo/GetFiscalYears  (empCodigo DINAMICO)
    Paso(44, 'GET', '{back}/api/services/app/GdcPeriodo/GetFiscalYears?empCodigo={emp}', '/api/services/app/GdcPeriodo/GetFiscalYears', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 45: POST GdC Back GdcPeriodo/GetPeriodosFiscales  (empCodigo DINAMICO)
    Paso(45, 'POST', '{back}/api/services/app/GdcPeriodo/GetPeriodosFiscales', '/api/services/app/GdcPeriodo/GetPeriodosFiscales', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'search': '', 'sort': {'field': 'periodoFiscalCod', 'direction': 'DESC'}, 'filter': {'empCodigo': v['emp']}}),
    # Paso 46: GET GdC Back GdcDashboard/GetUsageSummary  (emp+periodo DINAMICOS)
    Paso(46, 'GET', '{back}/api/services/app/GdcDashboard/GetUsageSummary?empCodigo={emp}&periodoId={periodo_id}', '/api/services/app/GdcDashboard/GetUsageSummary', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 47: POST GdcImpoOrigen/GetListForImport C-COMP-OrigenImpo=True
    Paso(47, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'ComprobanteCertificado': 'COMP', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 48: POST GdcImpoOrigen/GetListForImport V-COMP-OrigenImpo=True
    Paso(48, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'ComprobanteCertificado': 'COMP', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 49: POST GdcImpoOrigen/GetListForImport V-CERT-OrigenImpo=True
    Paso(49, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'ComprobanteCertificado': 'CERT', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 50: POST GdcImpoOrigen/GetListForImport C-CERT-OrigenImpo=True
    Paso(50, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'ComprobanteCertificado': 'CERT', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 51: POST Empresas/GetEmpresasByTenant 2
    Paso(51, 'POST', '{back}/api/services/app/Empresas/GetEmpresasByTenant', '/api/services/app/Empresas/GetEmpresasByTenant', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'filter': {'appModCod': 'GDC', 'activo': True}, 'search': ''}),
    # Paso 52: GET gestor-comprobantes-front /dashboard 2
    Paso(52, 'GET', '{front}/dashboard', '/dashboard', {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'}),
    # Paso 53: POST Empresas/GetEmpresasByTenant 3
    Paso(53, 'POST', '{back}/api/services/app/Empresas/GetEmpresasByTenant', '/api/services/app/Empresas/GetEmpresasByTenant', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'filter': {'appModCod': 'GDC', 'activo': True}, 'search': ''}),
    # Paso 54: GET Security/GetValidarToken 3
    Paso(54, 'GET', '{back}/api/services/app/Security/GetValidarToken', '/api/services/app/Security/GetValidarToken', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 55: GET Security/GetSecurity 2
    Paso(55, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 56: GET GdcConfig/GetLinks GDCLINKAYUDA 2
    Paso(56, 'GET', '{back}/api/services/app/GdcConfig/GetLinks?codigo=GDCLINKAYUDA', '/api/services/app/GdcConfig/GetLinks', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 57: GET GdcConfig/GetLinks GDCLINKNOVEDADES 2
    Paso(57, 'GET', '{back}/api/services/app/GdcConfig/GetLinks?codigo=GDCLINKNOVEDADES', '/api/services/app/GdcConfig/GetLinks', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 58: POST GdcImpoOrigen/GetListForImport V 2
    Paso(58, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'Activo': True, 'OrigenImpo': False}}),
    # Paso 59: POST GdcImpoOrigen/GetListForImport C 2
    Paso(59, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'Activo': True, 'OrigenImpo': False}}),
    # Paso 60: GET GdcPeriodo/GetFiscalYears empCodigo 2  (DINAMICO)
    Paso(60, 'GET', '{back}/api/services/app/GdcPeriodo/GetFiscalYears?empCodigo={emp}', '/api/services/app/GdcPeriodo/GetFiscalYears', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 61: POST GdcPeriodo/GetPeriodosFiscales empCodigo 2  (DINAMICO)
    Paso(61, 'POST', '{back}/api/services/app/GdcPeriodo/GetPeriodosFiscales', '/api/services/app/GdcPeriodo/GetPeriodosFiscales', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'search': '', 'sort': {'field': 'periodoFiscalCod', 'direction': 'DESC'}, 'filter': {'empCodigo': v['emp']}}),
    # Paso 62: GET GdcDashboard/GetUsageSummary 2  (DINAMICO)
    Paso(62, 'GET', '{back}/api/services/app/GdcDashboard/GetUsageSummary?empCodigo={emp}&periodoId={periodo_id}', '/api/services/app/GdcDashboard/GetUsageSummary', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 63: POST GdcImpoOrigen C-COMP-OrigenImpo=True 2  (DINAMICO)
    Paso(63, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'ComprobanteCertificado': 'COMP', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 64: POST GdcImpoOrigen V-COMP-OrigenImpo=True 2  (DINAMICO)
    Paso(64, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'ComprobanteCertificado': 'COMP', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 65: POST GdcImpoOrigen V-CERT-OrigenImpo=True 2  (DINAMICO)
    Paso(65, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'V', 'ComprobanteCertificado': 'CERT', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 66: POST GdcImpoOrigen C-CERT-OrigenImpo=True 2  (DINAMICO)
    Paso(66, 'POST', '{back}/api/services/app/GdcImpoOrigen/GetListForImport', '/api/services/app/GdcImpoOrigen/GetListForImport', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'forSeleccionOrigen': True, 'empCodigo': v['emp'], 'page': 1, 'limit': 100, 'sort': {'field': 'Descripcion', 'direction': 'ASC'}, 'search': '', 'filter': {'CompraVenta': 'C', 'ComprobanteCertificado': 'CERT', 'Activo': True, 'OrigenImpo': True}}),
    # Paso 67: GET front /dashboard/archivo/tipos-comprobante?_rsc=...
    Paso(67, 'GET', '{front}/dashboard/archivo/tipos-comprobante?_rsc=hi3jv', '/dashboard/archivo/tipos-comprobante', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 68: GET front /dashboard/empresa/trabajar-con-empresa?_rsc=...
    Paso(68, 'GET', '{front}/dashboard/empresa/trabajar-con-empresa?_rsc=hi3jv', '/dashboard/empresa/trabajar-con-empresa', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 69: GET front /dashboard/periodos-fiscales?_rsc=...
    Paso(69, 'GET', '{front}/dashboard/periodos-fiscales?_rsc=hi3jv', '/dashboard/periodos-fiscales', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 70: GET front /dashboard/comprobantes/compras?_rsc=...
    Paso(70, 'GET', '{front}/dashboard/comprobantes/compras?_rsc=hi3jv', '/dashboard/comprobantes/compras', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22comprobantes%22%2C%7B%22children%22%3A%5B%22compras%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 71: GET front /dashboard/iva/conciliacion-arca-comprobantes?_rsc=...
    Paso(71, 'GET', '{front}/dashboard/iva/conciliacion-arca-comprobantes?_rsc=hi3jv', '/dashboard/iva/conciliacion-arca-comprobantes', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 72: GET front /dashboard/emisiones/comprasy-ventas?_rsc=...
    Paso(72, 'GET', '{front}/dashboard/emisiones/comprasy-ventas?_rsc=hi3jv', '/dashboard/emisiones/comprasy-ventas', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 73: GET front /dashboard/exportaciones-varias/sicore-agentes-percepcion?_rsc=...
    Paso(73, 'GET', '{front}/dashboard/exportaciones-varias/sicore-agentes-percepcion?_rsc=hi3jv', '/dashboard/exportaciones-varias/sicore-agentes-percepcion', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 74: GET front /dashboard/contabilidad/asignar-cuentas?_rsc=...
    Paso(74, 'GET', '{front}/dashboard/contabilidad/asignar-cuentas?_rsc=hi3jv', '/dashboard/contabilidad/asignar-cuentas', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 75: GET front /dashboard/determinaciones-complementarias/pago-a-cuenta-idcb?_rsc=...
    Paso(75, 'GET', '{front}/dashboard/determinaciones-complementarias/pago-a-cuenta-idcb?_rsc=hi3jv', '/dashboard/determinaciones-complementarias/pago-a-cuenta-idcb', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 76: GET front /dashboard/utiles/exportar-holistor-win?_rsc=...
    Paso(76, 'GET', '{front}/dashboard/utiles/exportar-holistor-win?_rsc=hi3jv', '/dashboard/utiles/exportar-holistor-win', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 77: GET front /dashboard/comprobantes/ventas?_rsc=...
    Paso(77, 'GET', '{front}/dashboard/comprobantes/ventas?_rsc=hi3jv', '/dashboard/comprobantes/ventas', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 78: GET front /dashboard/comprobantes/certificados-emitidos?_rsc=...
    Paso(78, 'GET', '{front}/dashboard/comprobantes/certificados-emitidos?_rsc=hi3jv', '/dashboard/comprobantes/certificados-emitidos', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 79: GET front /dashboard/comprobantes/certificados-recibidos?_rsc=...
    Paso(79, 'GET', '{front}/dashboard/comprobantes/certificados-recibidos?_rsc=hi3jv', '/dashboard/comprobantes/certificados-recibidos', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 80: GET front /dashboard/comprobantes/movimientos-stock-agropecuario?_rsc=...
    Paso(80, 'GET', '{front}/dashboard/comprobantes/movimientos-stock-agropecuario?_rsc=hi3jv', '/dashboard/comprobantes/movimientos-stock-agropecuario', {'RSC': '1', 'Next-Router-Prefetch': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Next-Url': '/dashboard', 'Accept': '*/*'}),
    # Paso 81: GET GdC Back GdcLookups/GetProvincias
    Paso(81, 'GET', '{back}/api/services/app/GdcLookups/GetProvincias', '/api/services/app/GdcLookups/GetProvincias', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 82: GET GdC Back Security/GetSecurity 3
    Paso(82, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 83: POST GdC Back GdcComprobanteCompra/getGrid  (periodoCod + empCodigo DINAMICOS)
    Paso(83, 'POST', '{back}/api/services/app/GdcComprobanteCompra/getGrid', '/api/services/app/GdcComprobanteCompra/getGrid', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'filter': {'periodoFiscalCodDesde': v['periodo_cod'], 'periodoFiscalCodHasta': v['periodo_cod']}, 'empCodigo': v['emp'], 'periodoFiscalId': 0}),
    # Paso 84: GET GdcPeriodoFiscal/protegido  (emp+periodo DINAMICOS)
    Paso(84, 'GET', '{back}/api/services/app/GdcPeriodoFiscal/protegido?empCodigo={emp}&periodoFiscalId={periodo_id}', '/api/services/app/GdcPeriodoFiscal/protegido', {'Accept': '*/*'}),
    # Paso 85: GET front /dashboard/comprobantes/compras/new?_rsc=...
    Paso(85, 'GET', '{front}/dashboard/comprobantes/compras/new?_rsc=4f3l6', '/dashboard/comprobantes/compras/new', {'RSC': '1', 'Next-Url': '/dashboard/comprobantes/compras', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22comprobantes%22%2C%7B%22children%22%3A%5B%22compras%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Accept': '*/*'}),
    # Paso 86: POST Empresas/GetEmpresasByTenant CTB  (empCodigo DINAMICO)
    Paso(86, 'POST', '{back}/api/services/app/Empresas/GetEmpresasByTenant', '/api/services/app/Empresas/GetEmpresasByTenant', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'filter': {'appModCod': 'CTB', 'empCodigo': v['emp']}}),
    # Paso 87: GET Security/GetSecurity 4
    Paso(87, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 88: GET GdcLookups/GetMonedasAfip
    Paso(88, 'GET', '{back}/api/services/app/GdcLookups/GetMonedasAfip', '/api/services/app/GdcLookups/GetMonedasAfip', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 89: GET GdcLookups/GetTipoDocumento
    Paso(89, 'GET', '{back}/api/services/app/GdcLookups/GetTipoDocumento', '/api/services/app/GdcLookups/GetTipoDocumento', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 90: POST GdcTipoComprobante/Grid Compra
    Paso(90, 'POST', '{back}/api/services/app/GdcTipoComprobante/Grid', '/api/services/app/GdcTipoComprobante/Grid', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 0, 'sort': {'field': 'tipoComprobanteDesc', 'direction': 'ASC'}, 'filter': {'tipoComprobanteCompra': True, 'tipoComprobanteCertificado': False}}),
    # Paso 91: GET GdcLookups/GetAlicuotas
    Paso(91, 'GET', '{back}/api/services/app/GdcLookups/GetAlicuotas?includeInactive=false', '/api/services/app/GdcLookups/GetAlicuotas', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 92: GET GdcLookups/CondicionIva
    Paso(92, 'GET', '{back}/api/services/app/GdcLookups/CondicionIva', '/api/services/app/GdcLookups/CondicionIva', {'Accept': '*/*'}),
    # Paso 93: GET GdcEmpresas/11  (empCodigo DINAMICO en URL + name)
    Paso(93, 'GET', '{back}/api/services/app/GdcEmpresas/{emp}', '/api/services/app/GdcEmpresas/{emp}', {'Accept': '*/*'}),
    # Paso 94: GET GdcEmpresas/11/impositivo  (empCodigo DINAMICO en URL + name)
    Paso(94, 'GET', '{back}/api/services/app/GdcEmpresas/{emp}/impositivo', '/api/services/app/GdcEmpresas/{emp}/impositivo', {'Accept': '*/*'}),
    # Paso 95: GET GdcLookups/GetAlicuotasVigentes fecha  (FECHA DINAMICA HOY)
    Paso(95, 'GET', '{back}/api/services/app/GdcLookups/GetAlicuotasVigentes?fechaComprobante={fecha}', '/api/services/app/GdcLookups/GetAlicuotasVigentes', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 96: POST GdcLookups/GdcClienteProveedor/Consulta P  (empCodigo DINAMICO)
    Paso(96, 'POST', '{back}/api/services/app/GdcLookups/GdcClienteProveedor/Consulta', '/api/services/app/GdcLookups/GdcClienteProveedor/Consulta', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'empCodigo': v['emp'], 'tipoEntidad': 'P', 'page': 1, 'limit': 10, 'activo': True, 'filter': {'clienteProveedorProveedor': True}}),
    # Paso 97: GET GdcClienteProveedor/GetById  (empCodigo + id PROVEEDOR DINAMICOS)
    Paso(97, 'GET', '{back}/api/services/app/GdcClienteProveedor/GetById?empCodigo={emp}&id={prov_id}', '/api/services/app/GdcClienteProveedor/GetById', {'Accept': '*/*'}),
    # Paso 98: GET GdcClienteProveedor/Buscar  (TODOS params DINAMICOS: emp+tdoc+ndoc+periodo+clieprovId)
    Paso(98, 'GET', '{back}/api/services/app/GdcClienteProveedor/Buscar?empCodigo={emp}&tipoDoc={prov_tipo_doc}&nroDoc={prov_nro_doc}&periodoFiscalId={periodo_id}&clienteProveedorId={prov_id}', '/api/services/app/GdcClienteProveedor/Buscar', {'Accept': '*/*'}),
    # Paso 99: GET GdcLookups/GetAlicuotasVigentes fecha emision comprobante  (FECHA DINAMICA)
    Paso(99, 'GET', '{back}/api/services/app/GdcLookups/GetAlicuotasVigentes?fechaComprobante={fecha}', '/api/services/app/GdcLookups/GetAlicuotasVigentes', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 100: POST GdcLookups/getMovimientoTipoConsultaLookup GR-C  (empCodigo DINAMICO)
    Paso(100, 'POST', '{back}/api/services/app/GdcLookups/getMovimientoTipoConsultaLookup?empCodigo={emp}', '/api/services/app/GdcLookups/getMovimientoTipoConsultaLookup', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'sort': {'field': 'movimientoTipoDesc', 'direction': 'ASC'}, 'filter': {'MovimientoTipoClase': ['GR'], 'MovimientoTipoCpraVta': 'C', 'MovimientoTipoActivo': True}}),
    # Paso 101: GET GdcLookups/GetClasificacionARCA cpraVta=C
    Paso(101, 'GET', '{back}/api/services/app/GdcLookups/GetClasificacionARCA?cpraVta=C', '/api/services/app/GdcLookups/GetClasificacionARCA', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 102: POST GdcLookups/getMovimientoTipoConsultaLookup 2  (empCodigo DINAMICO)
    Paso(102, 'POST', '{back}/api/services/app/GdcLookups/getMovimientoTipoConsultaLookup?empCodigo={emp}', '/api/services/app/GdcLookups/getMovimientoTipoConsultaLookup', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'sort': {'field': 'movimientoTipoDesc', 'direction': 'ASC'}, 'filter': {'MovimientoTipoClase': ['GR'], 'MovimientoTipoCpraVta': 'C', 'MovimientoTipoActivo': True}}),

]

# Pasos 104 a 107: vuelta a la grilla después de crear.
DESPUES_GRILLA: list[Paso] = [
    # Paso 104: POST GdcComprobanteCompra/getGrid 2  (periodoCod + empCodigo DINAMICOS)
    Paso(104, 'POST', '{back}/api/services/app/GdcComprobanteCompra/getGrid', '/api/services/app/GdcComprobanteCompra/getGrid', {'Content-Type': 'application/json', 'Accept': '*/*'}, lambda v: {'page': 1, 'limit': 10, 'filter': {'periodoFiscalCodDesde': v['periodo_cod'], 'periodoFiscalCodHasta': v['periodo_cod']}, 'empCodigo': v['emp'], 'periodoFiscalId': 0}),
    # Paso 105: GET front /dashboard/comprobantes/compras?_rsc=yobna
    Paso(105, 'GET', '{front}/dashboard/comprobantes/compras?_rsc=yobna', '/dashboard/comprobantes/compras', {'RSC': '1', 'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22comprobantes%22%2C%7B%22children%22%3A%5B%22compras%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2C%22refetch%22%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D', 'Accept': '*/*'}),
    # Paso 106: GET GdcDashboard/GetUsageSummary 3  (DINAMICO)
    Paso(106, 'GET', '{back}/api/services/app/GdcDashboard/GetUsageSummary?empCodigo={emp}&periodoId={periodo_id}', '/api/services/app/GdcDashboard/GetUsageSummary', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 107: GET Security/GetSecurity 5
    Paso(107, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),

]

# Pasos 110 a 113: después del detalle del comprobante.
FINAL: list[Paso] = [
    # Paso 110: GET Security/GetSecurity 6
    Paso(110, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),
    # Paso 111: GET GdcEmpresaMovimientoTipoGravado/Get 1305  (movTipoId + empCodigo DINAMICOS)
    Paso(111, 'GET', '{back}/api/services/app/GdcEmpresaMovimientoTipoGravado/Get?movimientoTipoId={mov1}&empCodigo={emp}', '/api/services/app/GdcEmpresaMovimientoTipoGravado/Get', {'Accept': '*/*'}),
    # Paso 112: GET GdcEmpresaMovimientoTipoGravado/Get 1307  (movTipoId + empCodigo DINAMICOS)
    Paso(112, 'GET', '{back}/api/services/app/GdcEmpresaMovimientoTipoGravado/Get?movimientoTipoId={mov2}&empCodigo={emp}', '/api/services/app/GdcEmpresaMovimientoTipoGravado/Get', {'Accept': '*/*'}),
    # Paso 113: GET Security/GetSecurity 7 (fin)
    Paso(113, 'GET', '{back}/api/services/app/Security/GetSecurity?soloSuscripciones=false&soloPermisos=false', '/api/services/app/Security/GetSecurity', {'Content-Type': 'application/json', 'Accept': '*/*'}),

]
