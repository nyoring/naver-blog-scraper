import os
import re
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from config import DEFAULT_HOST, DEFAULT_PORT, BROWSERS_DIR, get_app_data_dir


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_base_dir() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def get_template_dir() -> Path:
    return get_base_dir() / "templates"


def check_chromium_available() -> bool:
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if browsers_path:
        search_dir = Path(browsers_path)
    else:
        if is_frozen():
            search_dir = get_app_data_dir() / BROWSERS_DIR
        else:
            search_dir = Path.home() / ".cache" / "ms-playwright"

    if not search_dir.exists():
        return False

    for entry in search_dir.iterdir():
        if entry.is_dir() and (
            entry.name.startswith("chromium-") or entry.name.startswith("chromium_")
        ):
            return True
    return False


def find_available_port(start_port: int = DEFAULT_PORT) -> int:
    for port in range(start_port, start_port + 11):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((DEFAULT_HOST, port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"No available port found in range {start_port}-{start_port + 10}"
    )


def install_chromium(progress_callback=None):
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not browsers_path:
        browsers_path = str(get_app_data_dir() / BROWSERS_DIR)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    if is_frozen():
        driver_dir = Path(sys._MEIPASS) / "playwright" / "driver"
        if sys.platform == "win32":
            driver_bin = driver_dir / "playwright.cmd"
        else:
            driver_bin = driver_dir / "playwright.sh"
        cmd = [str(driver_bin), "install", "chromium"]
    else:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    for line in iter(process.stdout.readline, ""):
        line = line.strip()
        if not line:
            continue
        if progress_callback:
            match = re.search(r"(\d+)%", line)
            percent = int(match.group(1)) if match else None
            progress_callback(percent, line)

    process.wait()

    try:
        import app as app_module

        if hasattr(app_module, "chromium_install_state"):
            app_module.chromium_install_state["status"] = "complete"
    except (ImportError, AttributeError):
        pass


def create_app():
    from app import app as flask_app

    if is_frozen():
        flask_app.template_folder = str(get_template_dir())

    return flask_app


def main():
    from waitress import serve

    flask_app = create_app()
    chromium_ok = check_chromium_available()
    port = find_available_port()
    url = f"http://{DEFAULT_HOST}:{port}"

    if not chromium_ok:
        try:
            import app as app_module

            if hasattr(app_module, "chromium_install_state"):
                app_module.chromium_install_state["status"] = "downloading"
        except (ImportError, AttributeError):
            pass

        install_thread = threading.Thread(target=install_chromium, daemon=True)
        install_thread.start()
        open_url = f"{url}/setup"
    else:
        open_url = url

    threading.Timer(1.5, webbrowser.open, args=[open_url]).start()

    try:
        serve(flask_app, host=DEFAULT_HOST, port=port)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
