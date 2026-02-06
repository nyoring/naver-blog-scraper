import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from config import APP_VERSION


def clean():
    for d in ["dist", "build"]:
        p = Path(d)
        if p.exists():
            shutil.rmtree(p)
            print(f"Removed {d}/")


def build_app():
    print("Building App.exe...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "app.spec", "--noconfirm", "--clean"],
        check=True,
    )
    return result.returncode == 0


def build_launcher():
    print("Building Launcher.exe...")
    result = subprocess.run(
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
    return result.returncode == 0


def create_release_zip(version: str) -> tuple[Path, Path]:
    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)

    app_zip = release_dir / f"NaverBlogScraper-App-v{version}.zip"
    launcher_zip = release_dir / f"NaverBlogScraper-Launcher-v{version}.zip"

    _zip_directory(Path("dist/App"), app_zip)
    _zip_directory(Path("dist/Launcher"), launcher_zip)

    print(f"Created {app_zip} ({app_zip.stat().st_size / 1024 / 1024:.1f} MB)")
    print(
        f"Created {launcher_zip} ({launcher_zip.stat().st_size / 1024 / 1024:.1f} MB)"
    )
    return app_zip, launcher_zip


def _zip_directory(source_dir: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in source_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(source_dir.parent))


def _sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_manifest(version: str, app_zip: Path, launcher_zip: Path) -> Path:
    manifest = app_zip.parent / "manifest.json"
    data = {
        "version": version,
        "app_sha256": _sha256(app_zip),
        "launcher_sha256": _sha256(launcher_zip),
    }
    with open(manifest, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Generated {manifest}")
    return manifest


def verify_build():
    checks = [
        ("dist/App/App.exe", "App executable"),
        ("dist/Launcher/Launcher.exe", "Launcher executable"),
    ]
    all_ok = True
    for path, desc in checks:
        if Path(path).exists():
            print(f"  OK: {desc}")
        else:
            print(f"  MISSING: {desc} ({path})")
            all_ok = False
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Build NaverBlogScraper executables")
    parser.add_argument("--app-only", action="store_true", help="Build App.exe only")
    parser.add_argument(
        "--launcher-only", action="store_true", help="Build Launcher.exe only"
    )
    parser.add_argument(
        "--clean", action="store_true", help="Clean build artifacts only"
    )
    parser.add_argument("--no-zip", action="store_true", help="Skip zip creation")
    args = parser.parse_args()

    version = APP_VERSION

    if args.clean:
        clean()
        return

    print(f"=== NaverBlogScraper Build v{version} ===")
    clean()

    if args.app_only:
        build_app()
    elif args.launcher_only:
        build_launcher()
    else:
        build_app()
        build_launcher()

    print("\n=== Verifying build ===")
    if not verify_build():
        print("Build verification FAILED")
        sys.exit(1)

    if not args.no_zip and not args.app_only and not args.launcher_only:
        print("\n=== Creating release artifacts ===")
        app_zip, launcher_zip = create_release_zip(version)
        generate_manifest(version, app_zip, launcher_zip)

    print("\n=== Build complete ===")


if __name__ == "__main__":
    main()
