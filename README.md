# Scraping NIT Bolivia

Herramientas en Python para consultar el **estado de un NIT** (Número de
Identificación Tributaria) en el portal del Servicio de Impuestos
Nacionales de Bolivia (SIAT):

> https://siat.impuestos.gob.bo/rnc/public/consultas-estado-nit

Este repositorio contiene **dos versiones** del scraper. Solo una de ellas
funciona contra el portal actual — se conservan ambas porque la diferencia
entre ellas es justamente la lección interesante del proyecto (ver
[¿Por qué dos versiones?](#por-qué-dos-versiones)).

| Script | Tecnología | ¿Funciona hoy? |
|---|---|---|
| [`consulta_nit_bolivia_playwright.py`](consulta_nit_bolivia_playwright.py) | Playwright + Firefox | ✅ Sí |
| [`consulta_nit_bolivia.py`](consulta_nit_bolivia.py) | requests + BeautifulSoup | ❌ No (la SPA no responde a peticiones HTTP simples) |

---

## ✅ `consulta_nit_bolivia_playwright.py` (recomendado)

Automatiza un navegador real (Firefox) para llenar el formulario de
"Consultas del Estado del NIT", presionar **Buscar** e interceptar la
respuesta JSON que la propia página obtiene de su API interna. Esto es
necesario porque el portal:

- Es una SPA en Angular que renderiza todo con JavaScript (no sirve hacer
  un `GET` y parsear el HTML).
- Pasa por un chequeo de sesión SSO de Keycloak ("3rd party check iframe")
  que **no se completa en Chrome/Chromium** (el navegador termina
  redirigiendo a `www.impuestos.gob.bo` con la página en blanco). En
  **Firefox** ese chequeo sí se completa y el formulario carga con
  normalidad — por eso el script usa Firefox.

### Instalación

```bash
pip install playwright openpyxl
python -m playwright install firefox
```

### Uso

```bash
# Consultar un solo NIT
python consulta_nit_bolivia_playwright.py --nit 555162024

# Consultar varios NITs desde un archivo de texto (uno por línea)
python consulta_nit_bolivia_playwright.py --archivo nits.txt

# Exportar resultados a Excel o CSV
python consulta_nit_bolivia_playwright.py --nit 555162024 --exportar resultado.xlsx
python consulta_nit_bolivia_playwright.py --archivo nits.txt --exportar resultados.csv

# Mostrar la ventana del navegador (por defecto corre en segundo plano)
python consulta_nit_bolivia_playwright.py --nit 555162024 --headed

# Ajustar la pausa entre consultas (segundos, por defecto 1.5)
python consulta_nit_bolivia_playwright.py --archivo nits.txt --delay 3
```

### Salida de ejemplo

```
[1/1] Consultando NIT: 555162024 ... -> GRUPO EBIM LTDA.

────────────────────────────────────────────────────────────
RESULTADOS:
────────────────────────────────────────────────────────────
  nit                       555162024
  consultado_en             2026-06-07 08:29:40
  razon_social              GRUPO EBIM LTDA.
  estado                    ACTIVO
  estado_actividad          VIGENTE
  tipo_contribuyente        PERSONA JURÍDICA
  regimen_contribuyente     REGIMEN GENERAL
```

Si se consulta más de un NIT y no se especifica `--exportar`, el script
genera automáticamente un CSV con marca de tiempo
(`resultados_nit_AAAAMMDD_HHMMSS.csv`).

---

## ❌ `consulta_nit_bolivia.py`

Versión inicial basada en `requests` + `BeautifulSoup`, pensada para un
flujo clásico de formulario HTML/CSRF. Se incluye como referencia, pero
**no obtiene resultados del portal actual**: el HTML que se descarga es
solo el "shell" vacío de la aplicación Angular (el contenido se genera
en el navegador vía JavaScript), por lo que ninguno de los endpoints o
parsers que intenta encuentra datos reales. Queda como ejemplo de por qué
este tipo de portales modernos requiere automatización de navegador en
lugar de peticiones HTTP directas.

---

## Por qué dos versiones

El enfoque "tradicional" (`requests` + parseo de HTML) es más rápido y
liviano, y funciona perfectamente contra portales que generan HTML en el
servidor. Pero el RNC del SIAT es una **Single Page Application** moderna
(Angular + Module Federation) protegida por un flujo de autenticación
silenciosa (Keycloak SSO check). Eso significa que:

1. El HTML inicial no contiene los datos — solo el "esqueleto" de la app.
2. Hace falta ejecutar JavaScript real para que el formulario aparezca y
   para obtener el token de autorización con el que la página consulta su
   API interna (`siatrest.impuestos.gob.bo/.../rest/cons/estado-nit/{nit}`).
3. Ese flujo de autenticación es además sensible al motor del navegador:
   en Chrome/Chromium el chequeo de sesión nunca responde y la aplicación
   redirige a la página de inicio del SIN; en Firefox se completa sin
   problema.

La versión con Playwright resuelve todo esto automatizando un navegador
real (Firefox) y capturando la respuesta JSON limpia que la propia página
recibe — el mismo dato que ve un usuario humano en pantalla.

---

## Notas y buenas prácticas

- Se incluye una pausa configurable (`--delay`, por defecto 1.5 s) entre
  consultas para no sobrecargar el portal.
- Este proyecto consulta **únicamente** el endpoint público de "Estado del
  NIT" del portal oficial del SIN, exactamente como lo haría un usuario
  desde su navegador. No evade ninguna protección ni accede a información
  privada — usa las mismas pantallas y datos disponibles públicamente.
- Los resultados dependen de la disponibilidad y estructura del portal del
  SIN; si el SIN actualiza su sitio, los selectores o el endpoint interno
  podrían cambiar y requerir ajustes en el script.

## Requisitos

- Python 3.10+
- [Playwright](https://playwright.dev/python/) (`pip install playwright`)
- Navegador Firefox de Playwright (`python -m playwright install firefox`)
- `openpyxl` (opcional, solo para exportar a `.xlsx`)
