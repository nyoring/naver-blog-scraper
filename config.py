import os
from pathlib import Path

APP_NAME = "NaverBlogScraper"
APP_VERSION = "1.0.0"
GITHUB_REPO = "nyoring/naver-blog-scraper"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"

LAUNCHER_DIR = "launcher"
APP_DIR = "app"
VERSIONS_DIR = "app/versions"
BROWSERS_DIR = "browsers"
DATA_DIR = "data"
LOGS_DIR = "data/logs"
EXPORTS_DIR = "data/exports"

CURRENT_JSON = "current.json"
STATE_JSON = "state.json"


def get_app_data_dir() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        return Path(localappdata) / APP_NAME
    return Path.home() / ".naver-blog-scraper"
