import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

from config import (
    APP_DIR,
    APP_NAME,
    APP_VERSION,
    BROWSERS_DIR,
    CURRENT_JSON,
    DATA_DIR,
    EXPORTS_DIR,
    GITHUB_API_URL,
    LAUNCHER_DIR,
    LOGS_DIR,
    STATE_JSON,
    VERSIONS_DIR,
    get_app_data_dir,
)

logger = logging.getLogger(__name__)

LOCK_FILE = "launcher.lock"
REQUIRED_DIRS = [
    LAUNCHER_DIR,
    APP_DIR,
    VERSIONS_DIR,
    BROWSERS_DIR,
    DATA_DIR,
    LOGS_DIR,
    EXPORTS_DIR,
]


def ensure_directory_structure(base_dir: Path):
    for d in REQUIRED_DIRS:
        (base_dir / d).mkdir(parents=True, exist_ok=True)


def load_state(launcher_dir: Path) -> dict:
    state_path = launcher_dir / STATE_JSON
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"etag": "", "last_check": ""}


def save_state(launcher_dir: Path, state: dict):
    state_path = launcher_dir / STATE_JSON
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def check_for_update(state: dict) -> dict | None:
    try:
        req = request.Request(GITHUB_API_URL)
        req.add_header("Accept", "application/vnd.github.v3+json")
        etag = state.get("etag", "")
        if etag:
            req.add_header("If-None-Match", etag)

        resp = request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))

        new_etag = resp.headers.get("ETag", "")
        if new_etag:
            state["etag"] = new_etag
        state["last_check"] = datetime.now(timezone.utc).isoformat()

        tag = data.get("tag_name", "")
        version = tag.lstrip("v")
        if version == APP_VERSION:
            return None

        zip_url = None
        for asset in data.get("assets", []):
            name = asset["name"]
            if name.endswith(".zip") and "App" in name:
                zip_url = asset["browser_download_url"]
                break

        if not zip_url:
            return None

        sha256 = ""
        body = data.get("body", "")
        match = re.search(r"SHA256:\s*([a-fA-F0-9]{64})", body)
        if match:
            sha256 = match.group(1).lower()

        return {"version": tag, "zip_url": zip_url, "sha256": sha256}

    except error.HTTPError as e:
        if e.code == 304:
            return None
        logger.warning("HTTP error checking for update: %s", e)
        return None
    except Exception as e:
        logger.warning("Error checking for update: %s", e)
        return None


def download_update(url: str, dest_path: Path, progress_callback=None) -> Path:
    req = request.Request(url)
    resp = request.urlopen(req, timeout=60)
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 8192

    with open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total > 0:
                progress_callback(downloaded / total * 100)

    return dest_path


def verify_sha256(file_path: Path, expected_hash: str) -> bool:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower() == expected_hash.lower()


def extract_and_install(zip_path: Path, version: str, versions_dir: Path) -> Path:
    target = versions_dir / version
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)
    return target


def atomic_swap_current(app_dir: Path, version: str, path: str):
    current_json = app_dir / CURRENT_JSON
    data = json.dumps({"version": version, "path": path}, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(app_dir), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, str(current_json))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def cleanup_old_versions(versions_dir: Path, keep: int = 2):
    if not versions_dir.exists():
        return
    dirs = [d for d in versions_dir.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    for old_dir in dirs[keep:]:
        shutil.rmtree(old_dir, ignore_errors=True)


def find_app_exe(app_dir: Path) -> Path | None:
    current_json = app_dir / CURRENT_JSON
    if not current_json.exists():
        return None
    try:
        with open(current_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("path", "")
        if not path:
            return None
        base = Path(path)
        exe_path = base / "App.exe"
        if exe_path.exists():
            return exe_path
        nested = base / "App" / "App.exe"
        if nested.exists():
            return nested
        return exe_path
    except (json.JSONDecodeError, KeyError):
        return None


def acquire_lock(base_dir: Path) -> bool:
    lock_path = base_dir / LOCK_FILE
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def release_lock(base_dir: Path):
    lock_path = base_dir / LOCK_FILE
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


class LauncherUI:
    def __init__(self):
        self._root = None
        self._status_label = None
        self._progress = None
        try:
            import tkinter as _tk
            from tkinter import ttk as _ttk

            self._root = _tk.Tk()
            self._root.title(f"{APP_NAME} Launcher")
            self._root.geometry("400x120")
            self._root.resizable(False, False)

            frame = _ttk.Frame(self._root, padding=20)
            frame.pack(fill=_tk.BOTH, expand=True)

            self._status_label = _ttk.Label(frame, text="Initializing...")
            self._status_label.pack(anchor=_tk.W)

            self._progress = _ttk.Progressbar(frame, length=360, mode="determinate")
            self._progress.pack(pady=(10, 0))

            self._root.update()
        except Exception:
            self._root = None

    def set_status(self, msg: str):
        if self._root and self._status_label:
            try:
                self._status_label.config(text=msg)
                self._root.update()
            except Exception:
                pass
        else:
            print(msg)

    def set_progress(self, percent: float):
        if self._root and self._progress:
            try:
                self._progress["value"] = min(percent, 100)
                self._root.update()
            except Exception:
                pass

    def close(self):
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None


def main():
    base_dir = get_app_data_dir()
    ensure_directory_structure(base_dir)

    if not acquire_lock(base_dir):
        logger.warning("Another launcher instance is running.")
        return

    ui = LauncherUI()

    try:
        ui.set_status("Checking for updates...")
        launcher_dir = base_dir / LAUNCHER_DIR
        state = load_state(launcher_dir)

        update_info = check_for_update(state)
        save_state(launcher_dir, state)

        if update_info:
            version = update_info["version"]
            zip_url = update_info["zip_url"]
            sha256 = update_info.get("sha256", "")

            ui.set_status(f"Downloading {version}...")
            dest = base_dir / LAUNCHER_DIR / f"{version}.zip"
            download_update(zip_url, dest, progress_callback=ui.set_progress)

            if sha256:
                ui.set_status("Verifying download...")
                if not verify_sha256(dest, sha256):
                    logger.error("SHA256 verification failed")
                    dest.unlink(missing_ok=True)
                    ui.set_status("Update verification failed.")
                    time.sleep(2)
                    ui.close()
                    release_lock(base_dir)
                    return

            ui.set_status("Installing update...")
            versions_dir = base_dir / VERSIONS_DIR
            install_path = extract_and_install(dest, version.lstrip("v"), versions_dir)
            atomic_swap_current(
                base_dir / APP_DIR, version.lstrip("v"), str(install_path)
            )
            cleanup_old_versions(versions_dir)
            dest.unlink(missing_ok=True)
            ui.set_status("Update installed.")

        ui.set_status("Launching application...")
        app_exe = find_app_exe(base_dir / APP_DIR)
        if app_exe and app_exe.exists():
            subprocess.Popen([str(app_exe)], cwd=str(app_exe.parent))
        else:
            ui.set_status("App.exe not found.")
            logger.error("App.exe not found at %s", app_exe)
            time.sleep(2)

    except Exception as e:
        logger.error("Launcher error: %s", e)
        ui.set_status(f"Error: {e}")
        time.sleep(3)
    finally:
        ui.close()
        release_lock(base_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
