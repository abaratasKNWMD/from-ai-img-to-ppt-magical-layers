from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from tkinter import BOTH, Button, Frame, Label, Tk, messagebox

import httpx
import uvicorn


APP_NAME = "Magical Layers"
HOST = "127.0.0.1"
DEFAULT_PORT = 8000
LOG_FILE = "magical_layers_launcher.log"


def main() -> None:
    os.chdir(_app_dir())
    _log(f"Starting {APP_NAME} from {Path.cwd()}")
    port = _find_port(DEFAULT_PORT)
    url = f"http://{HOST}:{port}"
    _log(f"Selected URL {url}")

    server_ref: dict[str, uvicorn.Server] = {}
    server_thread = threading.Thread(target=_run_server, args=(port, server_ref), daemon=True)
    server_thread.start()

    if _wait_until_ready(url):
        webbrowser.open(url)

    _show_window(url, server_ref, server_thread)


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _find_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        if _port_free(port):
            return port
    raise RuntimeError("No local port available for Magical Layers.")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, port)) != 0


def _run_server(port: int, server_ref: dict[str, uvicorn.Server]) -> None:
    try:
        from server import app

        config = uvicorn.Config(
            app,
            host=HOST,
            port=port,
            log_config=None,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server_ref["server"] = server
        server.run()
    except Exception:
        _log("Server thread failed:\n" + traceback.format_exc())


def _wait_until_ready(url: str, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200:
                _log(f"Server ready at {url}")
                return True
        except Exception:
            time.sleep(0.25)
    _log(f"Server did not become ready at {url}")
    return False


def _show_window(url: str, server_ref: dict[str, uvicorn.Server], server_thread: threading.Thread) -> None:
    root = Tk()
    root.title(APP_NAME)
    root.geometry("420x190")
    root.resizable(False, False)

    frame = Frame(root, padx=22, pady=18)
    frame.pack(fill=BOTH, expand=True)

    Label(frame, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack(anchor="w")
    Label(frame, text="Servidor local activo", font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))
    Label(frame, text=url, font=("Consolas", 10)).pack(anchor="w", pady=(4, 14))

    button_row = Frame(frame)
    button_row.pack(anchor="w", pady=(4, 0))
    Button(button_row, text="Abrir programa", command=lambda: webbrowser.open(url), width=16).pack(side="left")
    Button(button_row, text="Cerrar", command=lambda: _shutdown(root, server_ref, server_thread), width=12).pack(
        side="left", padx=(10, 0)
    )

    root.protocol("WM_DELETE_WINDOW", lambda: _shutdown(root, server_ref, server_thread))
    root.mainloop()


def _shutdown(root: Tk, server_ref: dict[str, uvicorn.Server], server_thread: threading.Thread) -> None:
    _log("Shutting down")
    server = server_ref.get("server")
    if server is not None:
        server.should_exit = True
    server_thread.join(timeout=4)
    try:
        root.destroy()
    except Exception:
        messagebox.showinfo(APP_NAME, "Magical Layers se está cerrando.")


def _log(message: str) -> None:
    try:
        path = _app_dir() / LOG_FILE
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
