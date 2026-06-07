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
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path
from playwright.async_api import async_playwright
from pydantic import BaseModel

from consulta_nit_bolivia_playwright import URL, consultar_nit

# ─── Estado del navegador (compartido durante la vida del proceso) ───────────

estado_navegador = {"playwright": None, "browser": None, "context": None, "page": None}
lock_consulta = asyncio.Lock()


async def _cargar_portal():
    """(Re)carga la página del portal y espera a que el formulario esté listo."""
    page = estado_navegador["page"]
    await page.goto(URL, timeout=60_000)
    await page.wait_for_selector("input[id^='mat-input']", timeout=60_000)
    await page.wait_for_timeout(1000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pw = await async_playwright().start()
    # Firefox: en Chrome/Chromium el chequeo SSO de Keycloak nunca responde
    # y la SPA termina redirigiendo fuera de la página de consulta.
    browser = await pw.firefox.launch(headless=True)
    context = await browser.new_context(locale="es-BO")
    page = await context.new_page()
    estado_navegador.update(playwright=pw, browser=browser, context=context, page=page)

    await _cargar_portal()
    yield

    await context.close()
    await browser.close()
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
    page = estado_navegador["page"]
    if page is None:
        raise HTTPException(status_code=503, detail="El navegador interno aún no está listo")

    async with lock_consulta:
        resultado = await consultar_nit(page, numero)

        # Si algo salió mal (timeout, redirección, sesión vencida) se
        # recarga el portal una sola vez y se reintenta antes de fallar.
        if resultado.get("estado", "").startswith("ERROR"):
            await _cargar_portal()
            resultado = await consultar_nit(page, numero)

    if "razon_social" in resultado:
        return Contribuyente(**resultado)

    detalle = resultado.get("estado", "No se pudo obtener información del NIT")
    if detalle.startswith("ERROR"):
        raise HTTPException(status_code=502, detail=detalle)
    raise HTTPException(status_code=404, detail=detalle)
