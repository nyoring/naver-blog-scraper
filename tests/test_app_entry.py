import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_is_frozen_detects_pyinstaller():
    from app_entry import is_frozen

    with patch.object(sys, "frozen", True, create=True):
        assert is_frozen() is True


def test_is_frozen_returns_false_normally():
    from app_entry import is_frozen

    with patch.object(sys, "frozen", False, create=True):
        assert is_frozen() is False


def test_get_template_dir_frozen(mock_frozen):
    from app_entry import get_template_dir

    result = get_template_dir()
    assert result == mock_frozen / "templates"
    assert result.exists()


def test_get_template_dir_normal():
    from app_entry import get_template_dir

    result = get_template_dir()
    expected = Path(__file__).parent.parent / "templates"
    assert result == expected


def test_check_chromium_available_when_missing(tmp_path):
    from app_entry import check_chromium_available

    empty_dir = tmp_path / "browsers"
    empty_dir.mkdir()
    with patch.dict("os.environ", {"PLAYWRIGHT_BROWSERS_PATH": str(empty_dir)}):
        assert check_chromium_available() is False


def test_find_available_port_default():
    from app_entry import find_available_port

    port = find_available_port(start_port=49200)
    assert 49200 <= port <= 49210


def test_find_available_port_fallback():
    from app_entry import find_available_port

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 49200))
    blocker.listen(1)
    try:
        port = find_available_port(start_port=49200)
        assert 49201 <= port <= 49210
    finally:
        blocker.close()


def test_create_app_returns_flask_app():
    from app_entry import create_app

    flask_app = create_app()
    assert flask_app is not None
    assert hasattr(flask_app, "route")
    assert hasattr(flask_app, "run")
