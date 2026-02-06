import os
import pytest


@pytest.fixture
def app_spec_content():
    spec_path = os.path.join(os.path.dirname(__file__), "..", "app.spec")
    with open(spec_path, "r") as f:
        return f.read()


@pytest.fixture
def launcher_spec_content():
    spec_path = os.path.join(os.path.dirname(__file__), "..", "launcher.spec")
    with open(spec_path, "r") as f:
        return f.read()


class TestAppSpec:
    def test_app_spec_exists(self):
        spec_path = os.path.join(os.path.dirname(__file__), "..", "app.spec")
        assert os.path.exists(spec_path), "app.spec file does not exist"

    def test_app_spec_contains_collect_all_playwright(self, app_spec_content):
        assert "collect_all('playwright')" in app_spec_content, (
            "app.spec must contain collect_all('playwright')"
        )

    def test_app_spec_contains_templates_datas(self, app_spec_content):
        assert "('templates', 'templates')" in app_spec_content, (
            "app.spec must contain templates in datas"
        )

    def test_app_spec_uses_onedir_pattern(self, app_spec_content):
        assert "COLLECT(" in app_spec_content, (
            "app.spec must use COLLECT for onedir pattern"
        )

    def test_app_spec_entry_point_is_app_entry(self, app_spec_content):
        assert "['app_entry.py']" in app_spec_content, (
            "app.spec entry point must be app_entry.py"
        )

    def test_app_spec_name_is_app(self, app_spec_content):
        assert "name='App'" in app_spec_content, (
            "app.spec executable name must be 'App'"
        )


class TestLauncherSpec:
    def test_launcher_spec_exists(self):
        spec_path = os.path.join(os.path.dirname(__file__), "..", "launcher.spec")
        assert os.path.exists(spec_path), "launcher.spec file does not exist"

    def test_launcher_spec_uses_onedir_pattern(self, launcher_spec_content):
        assert "COLLECT(" in launcher_spec_content, (
            "launcher.spec must use COLLECT for onedir pattern"
        )

    def test_launcher_spec_entry_point_is_launcher(self, launcher_spec_content):
        assert "['launcher.py']" in launcher_spec_content, (
            "launcher.spec entry point must be launcher.py"
        )

    def test_launcher_spec_name_is_launcher(self, launcher_spec_content):
        assert "name='Launcher'" in launcher_spec_content, (
            "launcher.spec executable name must be 'Launcher'"
        )

    def test_launcher_spec_excludes_playwright(self, launcher_spec_content):
        assert (
            "'playwright'" in launcher_spec_content
            and "excludes=" in launcher_spec_content
        ), "launcher.spec must exclude playwright"

    def test_launcher_spec_console_false(self, launcher_spec_content):
        assert "console=False" in launcher_spec_content, (
            "launcher.spec must have console=False"
        )
