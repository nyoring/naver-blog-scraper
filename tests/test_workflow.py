import os
import yaml
import pytest


WORKFLOW_PATH = ".github/workflows/release.yml"


def test_workflow_file_exists():
    assert os.path.exists(WORKFLOW_PATH), (
        f"Workflow file {WORKFLOW_PATH} does not exist"
    )


def test_workflow_valid_yaml():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    assert workflow is not None, "Workflow YAML is invalid"
    assert isinstance(workflow, dict), "Workflow should be a dictionary"


def test_workflow_triggered_on_tag_push():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    trigger = workflow.get(True) or workflow.get("on")
    assert trigger is not None, "Workflow should have 'on' trigger"
    assert "push" in trigger, "Workflow should trigger on push"
    assert "tags" in trigger["push"], "Workflow should trigger on tag push"
    assert trigger["push"]["tags"] == ["v*"], "Workflow should trigger on v* tags"


def test_workflow_uses_windows_runner():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    assert build_job["runs-on"] == "windows-latest", (
        "Build job should use windows-latest runner"
    )


def test_workflow_installs_python():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    python_setup = [s for s in steps if "actions/setup-python" in s.get("uses", "")]
    assert len(python_setup) > 0, "Build job should install Python"
    assert python_setup[0]["with"]["python-version"] == "3.12", "Should use Python 3.12"


def test_workflow_runs_pyinstaller_app():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    app_steps = [s for s in steps if "app.spec" in s.get("run", "")]
    assert len(app_steps) > 0, "Build job should run pyinstaller for app.spec"


def test_workflow_runs_pyinstaller_launcher():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    launcher_steps = [s for s in steps if "launcher.spec" in s.get("run", "")]
    assert len(launcher_steps) > 0, "Build job should run pyinstaller for launcher.spec"


def test_workflow_creates_release_zip():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    zip_steps = [s for s in steps if "Compress-Archive" in s.get("run", "")]
    assert len(zip_steps) > 0, "Build job should create release zips"


def test_workflow_generates_sha256():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    sha_steps = [s for s in steps if "Get-FileHash" in s.get("run", "")]
    assert len(sha_steps) > 0, "Build job should generate SHA256 hashes"


def test_workflow_uploads_to_release():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    build_job = workflow["jobs"]["build"]
    steps = build_job["steps"]
    release_steps = [
        s for s in steps if "softprops/action-gh-release" in s.get("uses", "")
    ]
    assert len(release_steps) > 0, "Build job should upload to GitHub release"


def test_workflow_runs_tests_first():
    with open(WORKFLOW_PATH, "r") as f:
        workflow = yaml.safe_load(f)
    assert "test" in workflow["jobs"], "Workflow should have test job"
    assert "build" in workflow["jobs"], "Workflow should have build job"
    build_job = workflow["jobs"]["build"]
    assert "needs" in build_job, "Build job should have needs"
    assert build_job["needs"] == "test", "Build job should need test job"
