"""
Ponto de entrada para o executavel desktop da Academia CTC.
Inicia o servidor FastAPI e mostra uma janela simples de controle.
"""
import os
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import Button, Label, Tk, messagebox

import uvicorn

PORT = 8000
URL = f"http://localhost:{PORT}"


def _prepare_desktop_stdio() -> None:
    if not getattr(sys, "frozen", False):
        return

    log_path = Path(sys.executable).with_name("desktop.log")
    if sys.stdout is None:
        sys.stdout = open(log_path, "a", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(log_path, "a", encoding="utf-8")


def _open_browser(root: Tk | None = None) -> None:
    opened = webbrowser.open(URL)
    if root is not None and not opened:
        messagebox.showwarning(
            "Academia CTC",
            f"Nao foi possivel abrir o navegador automaticamente.\nAcesse: {URL}",
            parent=root,
        )


def _run_server(server: uvicorn.Server) -> None:
    server.run()


def _show_control_window(server: uvicorn.Server, server_thread: threading.Thread) -> None:
    root = Tk()
    root.title("Academia CTC")
    root.resizable(False, False)
    root.geometry("360x190")

    Label(root, text="Academia CTC", font=("Segoe UI", 15, "bold")).pack(pady=(18, 4))
    Label(root, text="Sistema rodando neste computador.").pack()
    Label(root, text=URL, fg="#1456a0").pack(pady=(2, 14))

    Button(
        root,
        text="Abrir sistema",
        width=22,
        command=lambda: _open_browser(root),
    ).pack(pady=(0, 8))

    def close_app() -> None:
        server.should_exit = True
        root.destroy()

    Button(root, text="Encerrar", width=22, command=close_app).pack(pady=(0, 16))
    root.protocol("WM_DELETE_WINDOW", close_app)

    def watch_server() -> None:
        if server_thread.is_alive():
            root.after(500, watch_server)
            return
        if root.winfo_exists():
            root.destroy()

    root.after(1500, lambda: _open_browser(root))
    root.after(500, watch_server)
    root.mainloop()
    server.should_exit = True
    server_thread.join(timeout=5)


def main() -> None:
    _prepare_desktop_stdio()
    from main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    server_thread.start()
    _show_control_window(server, server_thread)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
