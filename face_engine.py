# -*- coding: utf-8 -*-
"""
face_engine.py
--------------
Motor de reconocimiento facial basado en InsightFace
(RetinaFace para detección + ArcFace para embeddings), ejecutado con
ONNX Runtime sobre CPU (`CPUExecutionProvider`).

Funciones principales:
  * get_embedding(image)              -> vector np.ndarray (512,) float32.
  * identify_student(emb, dict, thr)  -> mejor coincidencia por similitud
                                         del coseno o None.
"""

import io
from typing import Optional, Union

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image

import config

# ---------------------------------------------------------------------------
# Carga perezosa del modelo (singleton a nivel de módulo)
# ---------------------------------------------------------------------------
_face_app: Optional[FaceAnalysis] = None


def _get_face_app() -> FaceAnalysis:
    """
    Inicializa (una sola vez) el pipeline FaceAnalysis con el modelo
    configurado y lo devuelve. La primera llamada descarga los pesos ONNX.
    """
    global _face_app
    if _face_app is None:
        app = FaceAnalysis(
            name=config.MODEL_NAME,
            providers=config.MODEL_PROVIDERS,
        )
        # ctx_id = 0 -> primer provider disponible (CPU en este caso).
        app.prepare(ctx_id=0, det_size=config.DET_SIZE)
        _face_app = app
    return _face_app


# ---------------------------------------------------------------------------
# Utilidades de imagen
# ---------------------------------------------------------------------------
def _to_bgr_array(image: Union[bytes, np.ndarray]) -> np.ndarray:
    """
    Normaliza la entrada a un array BGR (formato OpenCV / InsightFace).

    Acepta bytes de imagen (JPEG/PNG/...) o un np.ndarray ya cargado.
    """
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:                       # Escala de grises -> BGR
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        elif arr.ndim == 3 and arr.shape[2] == 4:  # BGRA -> BGR
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        return arr

    # Bytes -> PIL (RGB) -> OpenCV (BGR)
    with Image.open(io.BytesIO(image)) as img:
        rgb = np.array(img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def detect_faces(image: Union[bytes, np.ndarray]) -> list:
    """
    Detecta rostros en la imagen y devuelve la lista de objetos Face de
    InsightFace (con bbox, landmarks y embedding de 512 dims).
    """
    app = _get_face_app()
    frame = _to_bgr_array(image)
    return app.get(frame)


# ---------------------------------------------------------------------------
# Extracción de embeddings
# ---------------------------------------------------------------------------
def get_embedding(image: Union[bytes, np.ndarray]) -> np.ndarray:
    """
    Extrae el embedding facial (512 dims, float32) del rostro más
    prominente de la imagen.

    Raises:
        ValueError: si no se detecta ningún rostro en la imagen.
    """
    faces = detect_faces(image)
    if not faces:
        raise ValueError("No se detectó ningún rostro en la imagen.")

    # Si hay varios rostros, se toma el de mayor área (más cercano a cámara).
    def _area(face) -> float:
        x1, y1, x2, y2 = face.bbox
        return float(max(0.0, x2 - x1) * max(0.0, y2 - y1))

    rostro_principal = max(faces, key=_area)
    embedding = np.asarray(rostro_principal.embedding, dtype=np.float32)

    if embedding.shape != (config.EMBEDDING_DIM,):
        raise ValueError(
            f"Dimensión inesperada del embedding: {embedding.shape}, "
            f"se esperaba ({config.EMBEDDING_DIM},)."
        )
    return embedding


def contar_rostros(image: Union[bytes, np.ndarray]) -> int:
    """Devuelve el número de rostros detectados en la imagen."""
    return len(detect_faces(image))


# ---------------------------------------------------------------------------
# Identificación (matching contra la base de datos)
# ---------------------------------------------------------------------------
def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similitud del coseno entre dos vectores (con normalización segura)."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def identify_student(
    captured_embedding: np.ndarray,
    student_embeddings_dict: dict[int, np.ndarray],
    threshold: float = config.UMBRAL_SIMILITUD,
) -> Optional[tuple[int, float]]:
    """
    Compara el embedding capturado contra todos los embeddings registrados
    usando similitud del coseno.

    Args:
        captured_embedding: vector (512,) del rostro capturado en el punto
                            de control.
        student_embeddings_dict: {estudiante_id: embedding} cargado desde
                                 la base de datos.
        threshold: similitud mínima para aceptar la coincidencia
                   (por defecto config.UMBRAL_SIMILITUD = 0.45).

    Returns:
        (estudiante_id, similitud) del mejor candidato si supera el umbral;
        None en caso contrario.
    """
    if not student_embeddings_dict:
        return None

    mejor_id: Optional[int] = None
    mejor_similitud: float = -1.0

    for estudiante_id, embedding_bd in student_embeddings_dict.items():
        sim = _cosine_similarity(captured_embedding, embedding_bd)
        if sim > mejor_similitud:
            mejor_similitud = sim
            mejor_id = estudiante_id

    if mejor_id is not None and mejor_similitud >= threshold:
        return mejor_id, mejor_similitud
    return None
