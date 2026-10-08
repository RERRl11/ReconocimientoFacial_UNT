# -*- coding: utf-8 -*-
"""
app.py
------
Aplicación FastAPI del Sistema de Control de Accesos Universitario
y Registro de Ingresantes.

Vistas (Jinja2):
  * GET /          -> Dashboard: panel de marcación + últimos registros.
  * GET /registro  -> Formulario de registro manual de ingresantes.
  * GET /historial -> Consulta del historial de accesos (filtros opcionales).

API REST:
  * POST /api/estudiantes/registrar -> alta de estudiante + embedding facial.
  * POST /api/acceso/marcar         -> marcación de INGRESO / SALIDA por rostro.
"""

import base64
import binascii
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import config
import database
import face_engine

# ---------------------------------------------------------------------------
# Inicialización de la aplicación
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sistema de Control de Accesos Universitario",
    description="Registro de ingresantes y marcación de acceso con "
                "reconocimiento facial (InsightFace + ONNX Runtime).",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

# Crear las tablas al arrancar la aplicación.
database.init_db()


# ---------------------------------------------------------------------------
# Modelos de entrada (API)
# ---------------------------------------------------------------------------
class MarcarAccesoRequest(BaseModel):
    """Cuerpo JSON enviado desde la cámara del punto de control."""

    imagen_base64: str = Field(
        ..., description="Fotograma codificado en base64 (data URL o puro)."
    )
    tipo_evento: str | None = Field(
        default=None,
        description="INGRESO o SALIDA. Si se omite, se alterna "
                    "automáticamente según el último evento del estudiante.",
    )


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _error(status_code: int, mensaje: str) -> JSONResponse:
    """Construye una respuesta de error JSON uniforme."""
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "mensaje": mensaje},
    )


def _decodificar_imagen_base64(imagen_base64: str) -> bytes:
    """
    Decodifica una imagen en base64. Acepta tanto data URLs
    ('data:image/jpeg;base64,...') como cadenas base64 puras.
    """
    payload = imagen_base64.strip()
    if payload.startswith("data:"):
        match = re.match(r"^data:image/[\w+.-]+;base64,(.+)$", payload, re.DOTALL)
        if not match:
            raise ValueError("Formato de data URL de imagen no válido.")
        payload = match.group(1)
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("La imagen enviada no es un base64 válido.") from exc


def _guardar_foto(contenido: bytes, codigo_estudiante: str, extension: str) -> str:
    """
    Guarda la foto del estudiante en static/uploads/fotos y devuelve la
    ruta pública (URL) del archivo.
    """
    nombre_seguro = re.sub(r"[^A-Za-z0-9_-]", "_", codigo_estudiante.strip())
    nombre_archivo = f"{nombre_seguro}{extension}"
    ruta_fisica: Path = config.FOTOS_DIR / nombre_archivo
    ruta_fisica.write_bytes(contenido)
    return f"/static/uploads/fotos/{nombre_archivo}"


# ---------------------------------------------------------------------------
# Vistas web
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["Vistas"])
async def dashboard(request: Request):
    """Dashboard principal: panel de marcación y tabla de últimos registros."""
    ultimos = database.obtener_ultimos_registros(limite=10)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "ultimos_registros": ultimos,
            "total_estudiantes": database.contar_estudiantes(),
            "umbral": config.UMBRAL_SIMILITUD,
        },
    )


@app.get("/registro", response_class=HTMLResponse, tags=["Vistas"])
async def formulario_registro(request: Request):
    """Formulario web para registrar manualmente a un ingresante."""
    return templates.TemplateResponse("registro.html", {"request": request})


@app.get("/historial", response_class=HTMLResponse, tags=["Vistas"])
async def historial(
    request: Request,
    q: str | None = None,
    fecha: str | None = None,
):
    """
    Vista de consulta del historial de accesos.

    Filtros (todos opcionales):
      * q     -> código de estudiante, nombres, apellidos o nombre completo.
      * fecha -> día exacto en formato 'YYYY-MM-DD'.
    """
    # Validar la fecha; si el formato es inválido se ignora el filtro.
    fecha_valida: str | None = None
    fecha_malformada = False
    if fecha and fecha.strip():
        try:
            datetime.strptime(fecha.strip(), "%Y-%m-%d")
            fecha_valida = fecha.strip()
        except ValueError:
            fecha_malformada = True

    registros = database.buscar_registros(texto=q, fecha=fecha_valida)
    return templates.TemplateResponse(
        "historial.html",
        {
            "request": request,
            "registros": registros,
            "q": (q or "").strip(),
            "fecha": (fecha or "").strip(),
            "total": len(registros),
            "fecha_malformada": fecha_malformada,
        },
    )


# ---------------------------------------------------------------------------
# API: Registro de estudiantes
# ---------------------------------------------------------------------------
@app.post("/api/estudiantes/registrar", tags=["API"])
async def registrar_estudiante(
    codigo_estudiante: str = Form(...),
    nombres: str = Form(...),
    apellidos: str = Form(...),
    carrera: str = Form(...),
    foto: UploadFile = File(...),
):
    """
    Registra un ingresante:
      1. Valida datos del formulario y la foto.
      2. Verifica que la foto contenga exactamente UN rostro.
      3. Extrae el embedding facial (512 dims, float32).
      4. Guarda todo en SQLite (embedding serializado como BLOB).
    """
    # --- Validación de campos de texto ------------------------------------
    campos = {
        "codigo_estudiante": codigo_estudiante.strip(),
        "nombres": nombres.strip(),
        "apellidos": apellidos.strip(),
        "carrera": carrera.strip(),
    }
    if any(not valor for valor in campos.values()):
        return _error(400, "Todos los campos del formulario son obligatorios.")

    if database.obtener_estudiante_por_codigo(codigo_estudiante):
        return _error(
            409,
            f"El código de estudiante '{codigo_estudiante}' ya está registrado.",
        )

    # --- Validación del archivo de foto -----------------------------------
    extension = Path(foto.filename or "").suffix.lower()
    if extension not in config.EXTENSIONES_PERMITIDAS:
        return _error(
            400,
            f"Formato de imagen no permitido ({extension or 'sin extensión'}). "
            f"Use: {', '.join(sorted(config.EXTENSIONES_PERMITIDAS))}.",
        )

    contenido = await foto.read()
    if not contenido:
        return _error(400, "El archivo de la foto está vacío.")
    if len(contenido) > config.MAX_FOTO_BYTES:
        limite_mb = config.MAX_FOTO_BYTES // (1024 * 1024)
        return _error(400, f"La foto supera el tamaño máximo de {limite_mb} MB.")

    # --- Procesamiento facial ---------------------------------------------
    try:
        rostros = face_engine.detect_faces(contenido)
    except Exception:
        return _error(400, "No se pudo leer la imagen. Verifique que sea una "
                           "foto válida.")

    if len(rostros) == 0:
        return _error(
            400,
            "No se detectó ningún rostro en la foto. Suba una foto frontal, "
            "nítida y con buena iluminación.",
        )
    if len(rostros) > 1:
        return _error(
            400,
            f"Se detectaron {len(rostros)} rostros en la foto. "
            "La foto de perfil debe contener un único rostro.",
        )

    try:
        embedding = face_engine.get_embedding(contenido)
    except ValueError as exc:
        return _error(400, str(exc))

    # --- Persistencia ------------------------------------------------------
    foto_path = _guardar_foto(contenido, codigo_estudiante, extension)
    try:
        estudiante_id = database.insertar_estudiante(
            codigo_estudiante=codigo_estudiante,
            nombres=nombres,
            apellidos=apellidos,
            carrera=carrera,
            embedding=embedding,
            foto_path=foto_path,
        )
    except sqlite3.IntegrityError:
        return _error(
            409,
            f"El código de estudiante '{codigo_estudiante}' ya está registrado.",
        )

    return {
        "ok": True,
        "mensaje": f"Estudiante {nombres} {apellidos} registrado correctamente.",
        "estudiante_id": estudiante_id,
        "foto_path": foto_path,
    }


# ---------------------------------------------------------------------------
# API: Marcación de acceso
# ---------------------------------------------------------------------------
@app.post("/api/acceso/marcar", tags=["API"])
async def marcar_acceso(payload: MarcarAccesoRequest):
    """
    Recibe un fotograma (base64) desde el punto de control, identifica al
    estudiante por similitud facial y registra el evento correspondiente:

      * Si `tipo_evento` viene definido ('INGRESO'/'SALIDA'), se respeta.
      * Si se omite, se alterna según el último evento del estudiante
        (último INGRESO -> ahora SALIDA; sin registros -> INGRESO).
    """
    # --- Validación del tipo de evento solicitado --------------------------
    tipo_solicitado = (
        payload.tipo_evento.strip().upper() if payload.tipo_evento else None
    )
    if tipo_solicitado is not None and tipo_solicitado not in ("INGRESO", "SALIDA"):
        return _error(400, "tipo_evento debe ser 'INGRESO' o 'SALIDA'.")

    # --- Decodificación y extracción del embedding -------------------------
    try:
        imagen_bytes = _decodificar_imagen_base64(payload.imagen_base64)
    except ValueError as exc:
        return _error(400, str(exc))

    try:
        rostros = face_engine.detect_faces(imagen_bytes)
    except Exception:
        return _error(400, "No se pudo procesar la imagen capturada.")

    if len(rostros) == 0:
        return _error(
            400,
            "No se detectó ningún rostro en la captura. "
            "Acérquese a la cámara y vuelva a intentarlo.",
        )

    try:
        embedding_capturado = face_engine.get_embedding(imagen_bytes)
    except ValueError as exc:
        return _error(400, str(exc))

    # --- Identificación contra la base de datos ----------------------------
    embeddings_bd = database.obtener_embeddings()
    if not embeddings_bd:
        return _error(
            404,
            "No hay estudiantes registrados en el sistema. "
            "Registre primero a los ingresantes.",
        )

    coincidencia = face_engine.identify_student(
        embedding_capturado,
        embeddings_bd,
        threshold=config.UMBRAL_SIMILITUD,
    )
    if coincidencia is None:
        return _error(
            404,
            "Rostro no reconocido. La similitud no superó el umbral "
            f"de {config.UMBRAL_SIMILITUD}. Acceso denegado.",
        )

    estudiante_id, similitud = coincidencia
    estudiante = database.obtener_estudiante_por_id(estudiante_id)
    if estudiante is None:
        return _error(500, "Inconsistencia interna: estudiante no encontrado.")

    # --- Determinación del tipo de evento ----------------------------------
    if tipo_solicitado:
        tipo_evento = tipo_solicitado
    else:
        ultimo = database.obtener_ultimo_evento(estudiante_id)
        tipo_evento = "SALIDA" if ultimo == "INGRESO" else "INGRESO"

    registro_id = database.insertar_registro_acceso(
        estudiante_id=estudiante_id,
        tipo_evento=tipo_evento,
        umbral_similitud=similitud,
    )

    return {
        "ok": True,
        "mensaje": f"{tipo_evento} registrado para "
                   f"{estudiante['nombres']} {estudiante['apellidos']}.",
        "registro_id": registro_id,
        "tipo_evento": tipo_evento,
        "similitud": round(similitud, 4),
        "estudiante": {
            "id": estudiante_id,
            "codigo_estudiante": estudiante["codigo_estudiante"],
            "nombres": estudiante["nombres"],
            "apellidos": estudiante["apellidos"],
            "carrera": estudiante["carrera"],
            "foto_path": estudiante["foto_path"],
        },
    }


@app.get("/api/health", tags=["API"])
async def health():
    """Endpoint de verificación de estado del servicio."""
    return {
        "ok": True,
        "estudiantes_registrados": database.contar_estudiantes(),
        "umbral_similitud": config.UMBRAL_SIMILITUD,
    }
