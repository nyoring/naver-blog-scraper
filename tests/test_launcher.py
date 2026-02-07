import hashlib
import json
import os
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib import error

import pytest

from launcher import (
    acquire_lock,
    atomic_swap_current,
    check_for_update,
    cleanup_old_versions,
    download_update,
    ensure_directory_structure,
    extract_and_install,
    find_app_exe,
    load_state,
    release_lock,
    save_state,
    verify_sha256,
)


def test_ensure_directory_structure_creates_all_dirs(tmp_path):
    ensure_directory_structure(tmp_path)
    expected = [
        "launcher",
        "app",
        "app/versions",
        "browsers",
        "data",
        "data/logs",
        "data/exports",
    ]
    for d in expected:
        assert (tmp_path / d).is_dir(), f"Missing directory: {d}"


def test_load_state_returns_defaults_when_missing(tmp_app_dir):
    state = load_state(tmp_app_dir / "launcher")
    assert state == {"etag": "", "last_check": ""}


def test_load_state_reads_existing(tmp_app_dir):
    launcher_dir = tmp_app_dir / "launcher"
    state_data = {"etag": '"abc123"', "last_check": "2025-01-01T00:00:00Z"}
    (launcher_dir / "state.json").write_text(json.dumps(state_data), encoding="utf-8")
    state = load_state(launcher_dir)
    assert state["etag"] == '"abc123"'
    assert state["last_check"] == "2025-01-01T00:00:00Z"


def test_save_state_writes_json(tmp_app_dir):
    launcher_dir = tmp_app_dir / "launcher"
    state_data = {"etag": '"xyz789"', "last_check": "2025-06-01T12:00:00Z"}
    save_state(launcher_dir, state_data)
    result = json.loads((launcher_dir / "state.json").read_text(encoding="utf-8"))
    assert result == state_data


@patch("launcher.request.urlopen")
def test_check_for_update_no_update(mock_urlopen):
    response_data = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "NaverBlogScraper-App-v1.0.0.zip",
                "browser_download_url": "https://example.com/v1.0.0.zip",
            }
        ],
        "body": "SHA256: " + "a" * 64,
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode()
    mock_resp.headers = {"ETag": '"etag1"'}
    mock_urlopen.return_value = mock_resp

    state = {"etag": "", "last_check": ""}
    result = check_for_update(state)
    assert result is None


@patch("launcher.request.urlopen")
def test_check_for_update_new_version(mock_urlopen, mock_github_api):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_github_api).encode()
    mock_resp.headers = {"ETag": '"new_etag"'}
    mock_urlopen.return_value = mock_resp

    state = {"etag": "", "last_check": ""}
    result = check_for_update(state)
    assert result is not None
    assert result["version"] == "v1.1.0"
    assert "v1.1.0" in result["zip_url"]
    assert state["etag"] == '"new_etag"'


@patch("launcher.request.urlopen")
def test_check_for_update_etag_cache(mock_urlopen):
    mock_urlopen.side_effect = error.HTTPError(
        url="", code=304, msg="Not Modified", hdrs={}, fp=None
    )
    state = {"etag": '"cached_etag"', "last_check": ""}
    result = check_for_update(state)
    assert result is None


@patch("launcher.request.urlopen")
def test_check_for_update_network_error(mock_urlopen):
    mock_urlopen.side_effect = ConnectionError("Network unreachable")
    state = {"etag": "", "last_check": ""}
    result = check_for_update(state)
    assert result is None


def test_download_and_verify_correct_sha256(tmp_path):
    test_content = b"hello world test content for sha256 verification"
    expected_hash = hashlib.sha256(test_content).hexdigest()

    serve_path = tmp_path / "test_download.bin"
    serve_path.write_bytes(test_content)
    dest_path = tmp_path / "downloaded.bin"

    with patch("launcher.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": str(len(test_content))}
        mock_resp.read = MagicMock(side_effect=[test_content, b""])
        mock_urlopen.return_value = mock_resp

        progress_values = []
        download_update(
            "https://example.com/test.zip",
            dest_path,
            progress_callback=lambda p: progress_values.append(p),
        )

    assert dest_path.exists()
    assert dest_path.read_bytes() == test_content
    assert verify_sha256(dest_path, expected_hash) is True
    assert len(progress_values) > 0


def test_download_and_verify_wrong_sha256(tmp_path):
    test_content = b"some file content"
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(test_content)
    assert verify_sha256(file_path, "0" * 64) is False


def test_extract_and_install_creates_version_dir(tmp_app_dir):
    versions_dir = tmp_app_dir / "app" / "versions"
    zip_path = tmp_app_dir / "test.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("App.exe", b"fake exe content")
        zf.writestr("config.ini", b"[settings]\nport=8000")

    result = extract_and_install(zip_path, "1.1.0", versions_dir)
    assert result == versions_dir / "1.1.0"
    assert (result / "App.exe").exists()
    assert (result / "config.ini").exists()


def test_atomic_swap_current_json(tmp_app_dir):
    app_dir = tmp_app_dir / "app"
    atomic_swap_current(app_dir, "1.1.0", "/some/path/to/1.1.0")
    current_json = app_dir / "current.json"
    assert current_json.exists()
    data = json.loads(current_json.read_text(encoding="utf-8"))
    assert data["version"] == "1.1.0"
    assert data["path"] == "/some/path/to/1.1.0"

    atomic_swap_current(app_dir, "1.2.0", "/some/path/to/1.2.0")
    data = json.loads(current_json.read_text(encoding="utf-8"))
    assert data["version"] == "1.2.0"


def test_cleanup_old_versions_keeps_two(tmp_app_dir):
    versions_dir = tmp_app_dir / "app" / "versions"
    for i, name in enumerate(["1.0.0", "1.1.0", "1.2.0", "1.3.0"]):
        d = versions_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "App.exe").write_bytes(b"x")
        mtime = 1000000 + i * 1000
        os.utime(str(d), (mtime, mtime))

    cleanup_old_versions(versions_dir, keep=2)
    remaining = sorted([d.name for d in versions_dir.iterdir() if d.is_dir()])
    assert len(remaining) == 2
    assert "1.2.0" in remaining
    assert "1.3.0" in remaining


def test_find_app_exe_returns_correct_path(tmp_app_dir):
    app_dir = tmp_app_dir / "app"
    version_path = tmp_app_dir / "app" / "versions" / "1.1.0"
    version_path.mkdir(parents=True, exist_ok=True)
    (version_path / "App.exe").write_bytes(b"fake exe")

    current = {"version": "1.1.0", "path": str(version_path)}
    (app_dir / "current.json").write_text(json.dumps(current), encoding="utf-8")

    result = find_app_exe(app_dir)
    assert result is not None
    assert result == version_path / "App.exe"

    assert find_app_exe(tmp_app_dir / "nonexistent") is None


def test_find_app_exe_returns_none_when_exe_missing(tmp_app_dir):
    app_dir = tmp_app_dir / "app"
    version_path = tmp_app_dir / "app" / "versions" / "1.1.0"
    version_path.mkdir(parents=True, exist_ok=True)

    current = {"version": "1.1.0", "path": str(version_path)}
    (app_dir / "current.json").write_text(json.dumps(current), encoding="utf-8")

    assert find_app_exe(app_dir) is None


def test_find_app_exe_finds_nested_exe(tmp_app_dir):
    app_dir = tmp_app_dir / "app"
    version_path = tmp_app_dir / "app" / "versions" / "1.2.0"
    nested_dir = version_path / "App"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "App.exe").write_bytes(b"fake exe")

    current = {"version": "1.2.0", "path": str(version_path)}
    (app_dir / "current.json").write_text(json.dumps(current), encoding="utf-8")

    result = find_app_exe(app_dir)
    assert result is not None
    assert result == nested_dir / "App.exe"


def test_single_instance_lock(tmp_path):
    assert acquire_lock(tmp_path) is True
    assert acquire_lock(tmp_path) is False

    release_lock(tmp_path)
    assert acquire_lock(tmp_path) is True
    release_lock(tmp_path)
