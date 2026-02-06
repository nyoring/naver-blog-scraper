import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from build import (
    build_app,
    build_launcher,
    clean,
    create_release_zip,
    generate_manifest,
    verify_build,
)


def test_build_script_imports():
    from build import (
        build_app,
        build_launcher,
        clean,
        create_release_zip,
        generate_manifest,
        verify_build,
    )

    assert callable(clean)
    assert callable(build_app)
    assert callable(build_launcher)
    assert callable(create_release_zip)
    assert callable(generate_manifest)
    assert callable(verify_build)


def test_clean_removes_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    dist_dir = tmp_path / "dist"
    build_dir = tmp_path / "build"
    dist_dir.mkdir()
    build_dir.mkdir()

    (dist_dir / "test.txt").write_text("test")
    (build_dir / "test.txt").write_text("test")

    clean()

    assert not dist_dir.exists()
    assert not build_dir.exists()


@patch("build.subprocess.run")
def test_build_app_calls_pyinstaller(mock_run):
    mock_run.return_value = MagicMock(returncode=0)

    result = build_app()

    assert result is True
    mock_run.assert_called_once_with(
        [sys.executable, "-m", "PyInstaller", "app.spec", "--noconfirm", "--clean"],
        check=True,
    )


@patch("build.subprocess.run")
def test_build_launcher_calls_pyinstaller(mock_run):
    mock_run.return_value = MagicMock(returncode=0)

    result = build_launcher()

    assert result is True
    mock_run.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "launcher.spec",
            "--noconfirm",
            "--clean",
        ],
        check=True,
    )


def test_create_release_zip_creates_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app_dir = tmp_path / "dist" / "App"
    launcher_dir = tmp_path / "dist" / "Launcher"
    app_dir.mkdir(parents=True)
    launcher_dir.mkdir(parents=True)

    (app_dir / "App.exe").write_text("fake app")
    (launcher_dir / "Launcher.exe").write_text("fake launcher")

    app_zip, launcher_zip = create_release_zip("1.0.0")

    assert app_zip.exists()
    assert launcher_zip.exists()
    assert app_zip.name == "NaverBlogScraper-App-v1.0.0.zip"
    assert launcher_zip.name == "NaverBlogScraper-Launcher-v1.0.0.zip"


def test_generate_manifest_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    release_dir = tmp_path / "release"
    release_dir.mkdir()

    app_zip = release_dir / "NaverBlogScraper-App-v1.0.0.zip"
    launcher_zip = release_dir / "NaverBlogScraper-Launcher-v1.0.0.zip"

    app_zip.write_bytes(b"fake app zip")
    launcher_zip.write_bytes(b"fake launcher zip")

    manifest_path = generate_manifest("1.0.0", app_zip, launcher_zip)

    assert manifest_path.exists()
    assert manifest_path.name == "manifest.json"

    with open(manifest_path) as f:
        data = json.load(f)

    assert "version" in data
    assert "app_sha256" in data
    assert "launcher_sha256" in data
    assert data["version"] == "1.0.0"
    assert isinstance(data["app_sha256"], str)
    assert isinstance(data["launcher_sha256"], str)
    assert len(data["app_sha256"]) == 64
    assert len(data["launcher_sha256"]) == 64


def test_generate_manifest_sha256_correct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    release_dir = tmp_path / "release"
    release_dir.mkdir()

    app_zip = release_dir / "NaverBlogScraper-App-v1.0.0.zip"
    launcher_zip = release_dir / "NaverBlogScraper-Launcher-v1.0.0.zip"

    app_content = b"fake app zip content"
    launcher_content = b"fake launcher zip content"

    app_zip.write_bytes(app_content)
    launcher_zip.write_bytes(launcher_content)

    expected_app_sha = hashlib.sha256(app_content).hexdigest()
    expected_launcher_sha = hashlib.sha256(launcher_content).hexdigest()

    manifest_path = generate_manifest("1.0.0", app_zip, launcher_zip)

    with open(manifest_path) as f:
        data = json.load(f)

    assert data["app_sha256"] == expected_app_sha
    assert data["launcher_sha256"] == expected_launcher_sha


def test_main_help():
    result = subprocess.run(
        [sys.executable, "build.py", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--app-only" in result.stdout
    assert "--launcher-only" in result.stdout
    assert "--clean" in result.stdout
