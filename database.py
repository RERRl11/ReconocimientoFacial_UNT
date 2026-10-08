# -*- coding: utf-8 -*-
"""
database.py
-----------
Capa de acceso a datos (SQLite) del Sistema de Control de Accesos.

Tablas:
  * estudiantes      -> datos del ingresante + embedding facial (BLOB).
  * registros_acceso -> eventos de INGRESO / SALIDA con su timestamp.

Los embeddings se almacenan como BLOB serializando el np.ndarray con
`ndarray.tobytes()` y se recuperan con `np.frombuffer(..., dtype=float32)`.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

import config


# ---------------------------------------------------------------------------
# Conexión e inicialización
# ---------------------------------------------------------------------------
def get_connection(db_path: Path = config.DB_PATH) -> sqlite3.Connection:
    """Devuelve una conexión SQLite con filas tipo dict y FK activadas."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path = config.DB_PATH) -> None:
    """Crea las tablas del sistema si no existen."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS estudiantes (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_estudiante TEXT    NOT NULL UNIQUE,
                nombres           TEXT    NOT NULL,
                apellidos         TEXT    NOT NULL,
                carrera           TEXT    NOT NULL,
                embedding_blob    BLOB    NOT NULL,
                foto_path         TEXT    NOT NULL,
                fecha_registro    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS registros_acceso (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                estudiante_id     INTEGER NOT NULL,
                tipo_evento       TEXT    NOT NULL
                                  CHECK (tipo_evento IN ('INGRESO', 'SALIDA')),
                timestamp         TEXT    NOT NULL,
                umbral_similitud  REAL    NOT NULL,
                FOREIGN KEY (estudiante_id)
                    REFERENCES estudiantes (id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_registros_estudiante
                ON registros_acceso (estudiante_id);
            CREATE INDEX IF NOT EXISTS idx_registros_timestamp
                ON registros_acceso (timestamp);
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Serialización de embeddings
# ---------------------------------------------------------------------------
def embedding_to_blob(embedding: np.ndarray) -> bytes:
    """Serializa un vector float32 de 512 dimensiones a bytes (BLOB)."""
    vec = np.ascontiguousarray(embedding, dtype=np.float32)
    return vec.tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    """Deserializa un BLOB de SQLite a un np.ndarray float32 de 512 dims."""
    vec = np.frombuffer(blob, dtype=np.float32)
    if vec.size != config.EMBEDDING_DIM:
        raise ValueError(
            f"Embedding corrupto en BD: se esperaban {config.EMBEDDING_DIM} "
            f"valores y se obtuvieron {vec.size}."
        )
    return vec


# ---------------------------------------------------------------------------
# Operaciones sobre estudiantes
# ---------------------------------------------------------------------------
def insertar_estudiante(
    codigo_estudiante: str,
    nombres: str,
    apellidos: str,
    carrera: str,
    embedding: np.ndarray,
    foto_path: str,
) -> int:
    """
    Inserta un estudiante nuevo y devuelve su ID.

    Lanza sqlite3.IntegrityError si el código de estudiante ya existe.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO estudiantes
                (codigo_estudiante, nombres, apellidos, carrera,
                 embedding_blob, foto_path, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                codigo_estudiante.strip(),
                nombres.strip(),
                apellidos.strip(),
                carrera.strip(),
                embedding_to_blob(embedding),
                foto_path,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def obtener_estudiante_por_codigo(codigo_estudiante: str) -> Optional[sqlite3.Row]:
    """Busca un estudiante por su código único. Devuelve None si no existe."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM estudiantes WHERE codigo_estudiante = ?",
            (codigo_estudiante.strip(),),
        ).fetchone()
    finally:
        conn.close()


def obtener_estudiante_por_id(estudiante_id: int) -> Optional[sqlite3.Row]:
    """Busca un estudiante por su ID primario. Devuelve None si no existe."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM estudiantes WHERE id = ?", (estudiante_id,)
        ).fetchone()
    finally:
        conn.close()


def obtener_embeddings() -> dict[int, np.ndarray]:
    """
    Devuelve un diccionario {estudiante_id: embedding (np.ndarray float32)}
    con todos los estudiantes registrados, listo para el motor de matching.
    """
    conn = get_connection()
    try:
        filas = conn.execute("SELECT id, embedding_blob FROM estudiantes").fetchall()
        return {fila["id"]: blob_to_embedding(fila["embedding_blob"]) for fila in filas}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Operaciones sobre registros de acceso
# ---------------------------------------------------------------------------
def insertar_registro_acceso(
    estudiante_id: int,
    tipo_evento: str,
    umbral_similitud: float,
) -> int:
    """Registra un evento de INGRESO o SALIDA y devuelve el ID del registro."""
    if tipo_evento not in ("INGRESO", "SALIDA"):
        raise ValueError(f"Tipo de evento inválido: {tipo_evento!r}")

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO registros_acceso
                (estudiante_id, tipo_evento, timestamp, umbral_similitud)
            VALUES (?, ?, ?, ?)
            """,
            (
                estudiante_id,
                tipo_evento,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                float(umbral_similitud),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def obtener_ultimo_evento(estudiante_id: int) -> Optional[str]:
    """
    Devuelve el tipo del último evento ('INGRESO' o 'SALIDA') de un
    estudiante, o None si nunca ha marcado. Se usa para alternar
    automáticamente INGRESO <-> SALIDA.
    """
    conn = get_connection()
    try:
        fila = conn.execute(
            """
            SELECT tipo_evento FROM registros_acceso
            WHERE estudiante_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (estudiante_id,),
        ).fetchone()
        return fila["tipo_evento"] if fila else None
    finally:
        conn.close()


def obtener_ultimos_registros(limite: int = 10) -> list[sqlite3.Row]:
    """
    Devuelve los últimos N registros de acceso unidos con los datos del
    estudiante, para mostrarlos en el dashboard. Incluye las columnas
    derivadas `fecha` y `hora` (separadas del timestamp).
    """
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT r.id,
                   r.tipo_evento,
                   r.timestamp,
                   substr(r.timestamp, 1, 10) AS fecha,
                   substr(r.timestamp, 12, 8) AS hora,
                   r.umbral_similitud,
                   e.codigo_estudiante,
                   e.nombres,
                   e.apellidos,
                   e.carrera
            FROM registros_acceso r
            JOIN estudiantes e ON e.id = r.estudiante_id
            ORDER BY r.timestamp DESC, r.id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    finally:
        conn.close()


def buscar_registros(
    texto: Optional[str] = None,
    fecha: Optional[str] = None,
    limite: int = 200,
) -> list[sqlite3.Row]:
    """
    Consulta el historial de accesos con filtros opcionales.

    Args:
        texto: cadena a buscar en el código de estudiante, nombres,
               apellidos o nombre completo ("nombres apellidos").
        fecha: fecha exacta en formato 'YYYY-MM-DD' para filtrar por día.
        limite: número máximo de registros a devolver.

    Returns:
        Lista de filas con los datos del acceso y del estudiante, incluidas
        las columnas derivadas `fecha` y `hora`.
    """
    condiciones: list[str] = []
    parametros: list = []

    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        condiciones.append(
            "(e.codigo_estudiante LIKE ? "
            " OR e.nombres LIKE ? "
            " OR e.apellidos LIKE ? "
            " OR (e.nombres || ' ' || e.apellidos) LIKE ?)"
        )
        parametros.extend([patron, patron, patron, patron])

    if fecha and fecha.strip():
        condiciones.append("substr(r.timestamp, 1, 10) = ?")
        parametros.append(fecha.strip())

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    conn = get_connection()
    try:
        return conn.execute(
            f"""
            SELECT r.id,
                   r.tipo_evento,
                   r.timestamp,
                   substr(r.timestamp, 1, 10) AS fecha,
                   substr(r.timestamp, 12, 8) AS hora,
                   r.umbral_similitud,
                   e.codigo_estudiante,
                   e.nombres,
                   e.apellidos,
                   e.carrera
            FROM registros_acceso r
            JOIN estudiantes e ON e.id = r.estudiante_id
            {where}
            ORDER BY r.timestamp DESC, r.id DESC
            LIMIT ?
            """,
            (*parametros, limite),
        ).fetchall()
    finally:
        conn.close()


def contar_estudiantes() -> int:
    """Devuelve el total de estudiantes registrados."""
    conn = get_connection()
    try:
        return int(conn.execute("SELECT COUNT(*) AS n FROM estudiantes").fetchone()["n"])
    finally:
        conn.close()
