"""
API REST (FastAPI) - Consulta Estado NIT Bolivia
Portal: https://siat.impuestos.gob.bo/rnc/public/consultas-estado-nit

Expone el scraper de consulta_nit_bolivia_playwright.py como una API HTTP.
Mantiene un único navegador Firefox (Playwright) abierto durante toda la
vida del proceso —cargar el portal toma ~10s por el chequeo SSO de
Keycloak— y reutiliza esa misma pestaña para cada consulta, serializadas
con un lock (el formulario no admite consultas concurrentes en paralelo).

Endpoints:
    GET /health       -> estado de la API y del navegador interno
    GET /nit/{numero} -> datos del contribuyente para ese NIT

Ejecutar:
    uvicorn api_nit_bolivia:app --host 0.0.0.0 --port 8000

Requisitos:
    pip install fastapi "uvicorn[standard]" playwright openpyxl
    python -m playwright install firefox
"""

import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path
from playwright.async_api import async_playwright
from pydantic import BaseModel

from consulta_nit_bolivia_playwright import URL, consultar_nit

# ─── Estado del navegador (compartido durante la vida del proceso) ───────────

estado_navegador = {"playwright": None, "browser": None, "context": None, "page": None}
lock_consulta = asyncio.Lock()


RECURSOS_PESADOS = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|woff2?|ttf|otf|mp4|webm)(\?.*)?$", re.IGNORECASE
)


async def _bloquear_recursos_pesados(route):
    await route.abort()


async def _nuevo_navegador():
    """Crea (o recrea) browser + contexto + página, y carga el portal.

    Se usa tanto al arrancar como para recuperarse de un crash: en planes
    gratuitos con poca RAM, Firefox puede morir a media consulta
    ("Page crashed" / "Target page... has been closed"), y la única forma
    de seguir sirviendo peticiones es descartar el navegador muerto y
    levantar uno nuevo desde cero (reusar la página fallida solo produce
    más errores en cascada).
    """
    pw = estado_navegador["playwright"]
    for clave in ("context", "browser"):
        objeto = estado_navegador.get(clave)
        if objeto is not None:
            try:
                await objeto.close()
            except Exception:
                pass

    # Firefox: en Chrome/Chromium el chequeo SSO de Keycloak nunca responde
    # y la SPA termina redirigiendo fuera de la página de consulta.
    browser = await pw.firefox.launch(
        headless=True,
        firefox_user_prefs={
            "browser.cache.disk.enable": False,
            "browser.cache.memory.enable": False,
            "browser.sessionhistory.max_total_viewers": 0,
            "media.autoplay.default": 5,
        },
    )
    context = await browser.new_context(locale="es-BO")
    page = await context.new_page()
    # Bloquear imágenes/fuentes/video reduce bastante el consumo de RAM de
    # Firefox; el formulario se ubica por selector/texto, no por apariencia.
    await page.route(RECURSOS_PESADOS, _bloquear_recursos_pesados)
    estado_navegador.update(browser=browser, context=context, page=page)

    await page.goto(URL, timeout=60_000)
    await page.wait_for_selector("input[id^='mat-input']", timeout=60_000)
    await page.wait_for_timeout(1000)
    return page


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    estado_navegador["playwright"] = pw
    await _nuevo_navegador()
    yield

    for clave in ("context", "browser"):
        objeto = estado_navegador.get(clave)
        if objeto is not None:
            try:
                await objeto.close()
            except Exception:
                pass
    await pw.stop()
    estado_navegador.update(playwright=None, browser=None, context=None, page=None)


app = FastAPI(
    title="API Consulta NIT Bolivia",
    description="Consulta el estado de un NIT en el portal SIAT (RNC) del Servicio de Impuestos Nacionales de Bolivia.",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Modelos de respuesta ─────────────────────────────────────────────────────

class Contribuyente(BaseModel):
    nit: str
    consultado_en: str
    razon_social: str
    estado: str
    estado_actividad: str
    tipo_contribuyente: str
    regimen_contribuyente: str


class ErrorRespuesta(BaseModel):
    detail: str


class SaludRespuesta(BaseModel):
    status: str
    navegador_listo: bool


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=SaludRespuesta, summary="Verifica que la API y el navegador interno funcionan")
async def health():
    page = estado_navegador["page"]
    listo = page is not None and not page.is_closed()
    return SaludRespuesta(status="ok" if listo else "degradado", navegador_listo=listo)


@app.get(
    "/nit/{numero}",
    response_model=Contribuyente,
    responses={404: {"model": ErrorRespuesta}, 502: {"model": ErrorRespuesta}},
    summary="Consulta el estado de un NIT",
)
async def obtener_nit(
    numero: str = Path(..., pattern=r"^\d+$", description="Número de NIT a consultar (solo dígitos)")
):
    if estado_navegador["page"] is None:
        raise HTTPException(status_code=503, detail="El navegador interno aún no está listo")

    async with lock_consulta:
        try:
            resultado = await consultar_nit(estado_navegador["page"], numero)
            if resultado.get("estado", "").startswith("ERROR"):
                raise RuntimeError(resultado["estado"])
        except Exception:
            # El navegador pudo haberse caído (crash por memoria, sesión
            # vencida, "Target page... has been closed", etc.): se relanza
            # desde cero y se reintenta la consulta una sola vez.
            try:
                page = await _nuevo_navegador()
                resultado = await consultar_nit(page, numero)
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"ERROR: no se pudo recuperar el navegador interno ({e})",
                )

    if "razon_social" in resultado:
        return Contribuyente(**resultado)

    detalle = resultado.get("estado", "No se pudo obtener información del NIT")
    if detalle.startswith("ERROR"):
        raise HTTPException(status_code=502, detail=detalle)
    raise HTTPException(status_code=404, detail=detalle)
