"""공통 pytest fixtures"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_app_dir(tmp_path):
    """NaverBlogScraper 디렉토리 구조를 임시 디렉토리에 생성"""
    dirs = [
        "launcher",
        "app",
        "app/versions",
        "browsers",
        "data",
        "data/logs",
        "data/exports",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def mock_frozen(tmp_path):
    """PyInstaller frozen 상태를 모킹"""
    meipass = tmp_path / "_MEIPASS"
    meipass.mkdir(exist_ok=True)
    (meipass / "templates").mkdir(exist_ok=True)

    with (
        patch.object(sys, "frozen", True, create=True),
        patch.object(sys, "_MEIPASS", str(meipass), create=True),
    ):
        yield meipass


@pytest.fixture
def mock_github_api():
    """GitHub Releases API 응답 모킹"""
    return {
        "tag_name": "v1.1.0",
        "name": "v1.1.0",
        "assets": [
            {
                "name": "NaverBlogScraper-App-v1.1.0.zip",
                "browser_download_url": "https://github.com/nyoring/naver-blog-scraper/releases/download/v1.1.0/NaverBlogScraper-App-v1.1.0.zip",
                "size": 50000000,
            },
            {
                "name": "manifest.json",
                "browser_download_url": "https://github.com/nyoring/naver-blog-scraper/releases/download/v1.1.0/manifest.json",
            },
        ],
        "body": "## NaverBlogScraper v1.1.0\n\nSHA256: abc123def456",
    }
