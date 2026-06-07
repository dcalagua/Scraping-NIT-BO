# Scraping NIT Bolivia

Herramientas en Python para consultar el **estado de un NIT** (Número de
Identificación Tributaria) en el portal del Servicio de Impuestos
Nacionales de Bolivia (SIAT):

> https://siat.impuestos.gob.bo/rnc/public/consultas-estado-nit

El repositorio incluye un script de línea de comandos y una **API REST**
construida sobre el mismo motor de consulta. También se conserva una
primera versión del scraper que **no funciona** contra el portal actual —
se incluye porque la diferencia entre ambas es justamente la lección
interesante del proyecto (ver [¿Por qué dos versiones?](#por-qué-dos-versiones)).

| Archivo | Qué es | Tecnología | ¿Funciona hoy? |
|---|---|---|---|
| [`consulta_nit_bolivia_playwright.py`](consulta_nit_bolivia_playwright.py) | Script CLI | Playwright + Firefox | ✅ Sí |
| [`api_nit_bolivia.py`](api_nit_bolivia.py) | API REST | FastAPI + Playwright + Firefox | ✅ Sí |
| [`consulta_nit_bolivia.py`](consulta_nit_bolivia.py) | Script CLI (versión inicial) | requests + BeautifulSoup | ❌ No (la SPA no responde a peticiones HTTP simples) |

También incluye [`Dockerfile`](Dockerfile), [`railway.json`](railway.json) y
[`render.yaml`](render.yaml) para desplegar la API gratis en Railway o
Render (ver [🚀 Despliegue](#-despliegue-railway--render-capa-gratuita)).

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

## ✅ `api_nit_bolivia.py` — API REST con FastAPI

Expone el mismo motor de consulta como una API HTTP con
[FastAPI](https://fastapi.tiangolo.com/). Al iniciar, levanta **un único
navegador Firefox** (vía Playwright) y lo deja autenticado contra el
portal durante toda la vida del proceso — cargarlo toma ~10 s por el
chequeo SSO de Keycloak. Cada solicitud reutiliza esa misma pestaña; las
consultas se serializan con un lock porque el formulario no admite
envíos en paralelo, y si una consulta falla (timeout, sesión vencida) la
API recarga el portal una vez y reintenta automáticamente.

### Instalación

```bash
pip install -r requirements.txt
python -m playwright install firefox
```

### Ejecutar

```bash
uvicorn api_nit_bolivia:app --host 0.0.0.0 --port 8000
```

Documentación interactiva (Swagger UI) disponible en `http://localhost:8000/docs`.

### Endpoints

#### `GET /health`

Verifica que la API y el navegador interno están operativos.

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok", "navegador_listo": true}
```

#### `GET /nit/{numero}`

Devuelve los datos del contribuyente para el NIT indicado (solo dígitos).

```bash
curl http://localhost:8000/nit/555162024
```
```json
{
  "nit": "555162024",
  "consultado_en": "2026-06-07 09:22:26",
  "razon_social": "GRUPO EBIM LTDA.",
  "estado": "ACTIVO",
  "estado_actividad": "VIGENTE",
  "tipo_contribuyente": "PERSONA JURÍDICA",
  "regimen_contribuyente": "REGIMEN GENERAL"
}
```

Respuestas de error:

| Código | Caso | Ejemplo de cuerpo |
|---|---|---|
| `404` | NIT no encontrado en el RNC | `{"detail": "No se encontro informacion de contribuyente con Nit: 1"}` |
| `422` | El número de NIT no es válido (no son solo dígitos) | `{"detail": [...]}` (validación automática de FastAPI) |
| `502` | El portal del SIN no respondió o falló la consulta | `{"detail": "ERROR: ..."}` |
| `503` | El navegador interno todavía no terminó de iniciar | `{"detail": "El navegador interno aún no está listo"}` |

### 🚀 Despliegue (Railway / Render, capa gratuita)

El repositorio incluye todo lo necesario para desplegar `api_nit_bolivia.py`
como contenedor Docker en **Railway** o **Render**, ambos con planes
gratuitos:

| Archivo | Para qué sirve |
|---|---|
| [`Dockerfile`](Dockerfile) | Imagen `python:3.12-slim` + Firefox de Playwright (`playwright install --with-deps firefox`) y arranque con `uvicorn`, escuchando en `$PORT` |
| [`.dockerignore`](.dockerignore) | Evita copiar `.git`, cachés y archivos exportados a la imagen |
| [`railway.json`](railway.json) | Configuración de Railway: build con Dockerfile y healthcheck en `/health` |
| [`render.yaml`](render.yaml) | Blueprint de Render: servicio web Docker en el plan `free` con healthcheck en `/health` |

#### Opción A — Railway

1. Crea un proyecto nuevo en [railway.app](https://railway.app/) y elige
   **Deploy from GitHub repo**, seleccionando `Scraping-NIT-BO`.
2. Railway detecta el `Dockerfile` automáticamente (el `railway.json`
   confirma el builder y define el healthcheck en `/health`).
3. No hace falta configurar ninguna variable de entorno: Railway inyecta
   `$PORT` y el `CMD` del Dockerfile ya lo usa.
4. Al finalizar el build, Railway expone una URL pública tipo
   `https://<tu-servicio>.up.railway.app` — prueba `/health` y
   `/nit/555162024`.

#### Opción B — Render

1. En [render.com](https://render.com/) elige **New → Blueprint** y conecta
   el repositorio `Scraping-NIT-BO` (Render leerá `render.yaml`
   automáticamente), o bien **New → Web Service** seleccionando
   *Environment: Docker* manualmente.
2. Selecciona el plan **Free**. Render construye la imagen con el
   `Dockerfile`, define `$PORT` automáticamente y usa `/health` como
   healthcheck (ya configurado en `render.yaml`).
3. Al terminar el deploy obtendrás una URL pública tipo
   `https://api-nit-bolivia.onrender.com`.

#### Notas importantes sobre el despliegue

- **Memoria**: un navegador Firefox real consume bastante más RAM que una
  API típica. Las capas gratuitas de Railway y Render rondan ~512 MB; si
  el servicio se reinicia o falla el `/health` por falta de memoria,
  considera subir de plan o limitar el navegador (por ejemplo, cerrando y
  reabriendo el contexto entre consultas en lugar de mantenerlo siempre
  activo).
- **Arranque en frío (cold start)**: el plan gratuito de Render "duerme"
  el servicio tras ~15 minutos sin tráfico; la primera petición tras
  despertar puede tardar bastante porque, además de reactivar el
  contenedor, la API debe levantar Firefox y completar el chequeo SSO de
  Keycloak (~10 s). El `healthCheckPath: /health` ayuda a la plataforma a
  esperar a que el navegador esté listo antes de enrutar tráfico.
- **Build más lento la primera vez**: `playwright install --with-deps
  firefox` descarga el navegador y sus dependencias del sistema durante el
  build de la imagen, lo que puede tardar varios minutos en el primer
  despliegue (las siguientes veces se reutiliza la capa cacheada si no
  cambia `requirements.txt`).
- **Probar la imagen localmente** (requiere Docker):
  ```bash
  docker build -t api-nit-bolivia .
  docker run --rm -p 8000:8000 api-nit-bolivia
  curl http://localhost:8000/health
  ```

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
- [Playwright](https://playwright.dev/python/) y su navegador Firefox
  (`python -m playwright install firefox`)
- `openpyxl` — solo para exportar a `.xlsx` desde el script CLI
- `fastapi` y `uvicorn[standard]` — solo para ejecutar `api_nit_bolivia.py`

Instalación de todo lo anterior de una vez:

```bash
pip install -r requirements.txt
python -m playwright install firefox
```
