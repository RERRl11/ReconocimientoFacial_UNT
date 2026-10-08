# -*- coding: utf-8 -*-
"""
main.py
-------
Punto de entrada principal del Sistema de Control de Accesos Universitario.

Uso:
    python main.py

Levanta el servidor Uvicorn sirviendo la aplicación FastAPI definida
en app.py, usando el host y puerto configurados en config.py.
"""

import uvicorn

import config
import database


def main() -> None:
    """Inicializa la base de datos y arranca el servidor web."""
    database.init_db()
    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
