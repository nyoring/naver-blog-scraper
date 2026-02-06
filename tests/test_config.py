import re
from unittest.mock import patch

import pytest


def test_app_name_is_string():
    from config import APP_NAME

    assert isinstance(APP_NAME, str) and len(APP_NAME) > 0


def test_version_format():
    from config import APP_VERSION

    assert re.match(r"\d+\.\d+\.\d+", APP_VERSION)


def test_github_repo():
    from config import GITHUB_REPO

    assert GITHUB_REPO == "nyoring/naver-blog-scraper"


def test_github_api_url_format():
    from config import GITHUB_API_URL, GITHUB_REPO

    assert GITHUB_REPO in GITHUB_API_URL
    assert "/releases/latest" in GITHUB_API_URL


def test_default_port():
    from config import DEFAULT_PORT

    assert isinstance(DEFAULT_PORT, int)
    assert DEFAULT_PORT == 8000


def test_app_data_dir_uses_localappdata():
    from config import get_app_data_dir

    with patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\test\\AppData\\Local"}):
        result = get_app_data_dir()
        assert "NaverBlogScraper" in str(result)


def test_app_data_dir_fallback():
    from config import get_app_data_dir

    with patch.dict("os.environ", {}, clear=True):
        result = get_app_data_dir()
        assert ".naver-blog-scraper" in str(result)


def test_subdirectory_constants():
    from config import (
        LAUNCHER_DIR,
        APP_DIR,
        BROWSERS_DIR,
        DATA_DIR,
        LOGS_DIR,
        EXPORTS_DIR,
    )

    for name in [LAUNCHER_DIR, APP_DIR, BROWSERS_DIR, DATA_DIR, LOGS_DIR, EXPORTS_DIR]:
        assert isinstance(name, str) and len(name) > 0


def test_current_json_filename():
    from config import CURRENT_JSON

    assert CURRENT_JSON == "current.json"


def test_state_json_filename():
    from config import STATE_JSON

    assert STATE_JSON == "state.json"
