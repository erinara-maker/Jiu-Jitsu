"""
Ponto de entrada para o executavel desktop da Academia CTC.
Inicia o servidor FastAPI e abre o navegador automaticamente.
"""
import sys
import threading
import time
import webbrowser

import uvicorn

PORT = 8000
URL = f"http://localhost:{PORT}"


def _open_browser() -> None:
    time.sleep(1.5)
    webbrowser.open(URL)


def main() -> None:
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
