# -*- coding: utf-8 -*-
"""
config.py
---------
Parámetros globales del Sistema de Control de Accesos Universitario.

Centraliza rutas, umbrales y constantes para evitar valores "mágicos"
dispersos por el código.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent

STATIC_DIR: Path = BASE_DIR / "static"
TEMPLATES_DIR: Path = BASE_DIR / "templates"
UPLOADS_DIR: Path = STATIC_DIR / "uploads"
FOTOS_DIR: Path = UPLOADS_DIR / "fotos"          # Fotos de perfil de estudiantes

DB_PATH: Path = BASE_DIR / "control_accesos.db"  # Archivo SQLite

# ---------------------------------------------------------------------------
# Motor de reconocimiento facial (InsightFace)
# ---------------------------------------------------------------------------
MODEL_NAME: str = "buffalo_l"                     # Modelo ArcFace/RetinaFace
MODEL_PROVIDERS: list[str] = ["CPUExecutionProvider"]
DET_SIZE: tuple[int, int] = (640, 640)            # Tamaño de entrada del detector

EMBEDDING_DIM: int = 512                          # Dimensión del vector ArcFace
EMBEDDING_DTYPE: str = "float32"

# ---------------------------------------------------------------------------
# Reglas de negocio
# ---------------------------------------------------------------------------
UMBRAL_SIMILITUD: float = 0.45   # Similitud de coseno mínima para aceptar match

# Dimensiones estándar para normalizar las imágenes procesadas
IMG_WIDTH: int = 640
IMG_HEIGHT: int = 480

# Tamaño máximo de foto permitido en el registro (5 MB)
MAX_FOTO_BYTES: int = 5 * 1024 * 1024

# Extensiones de imagen permitidas
EXTENSIONES_PERMITIDAS: set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
HOST: str = "0.0.0.0"
PORT: int = 8000

# ---------------------------------------------------------------------------
# Garantizar que las carpetas de trabajo existan al importar la configuración
# ---------------------------------------------------------------------------
for _carpeta in (STATIC_DIR, TEMPLATES_DIR, UPLOADS_DIR, FOTOS_DIR):
    _carpeta.mkdir(parents=True, exist_ok=True)
