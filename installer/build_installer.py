#!/usr/bin/env python
"""
build_installer.py - Creates the official open-source Inno Setup installer.

Usage:
    python installer/build_installer.py
    python installer/build_installer.py --version 1.0.0
    python installer/build_installer.py --output-name Tasks_Setup

What it does:
  1. Verifies/downloads official Python 3.12 installer for offline bundling.
  2. Copies only clean source files into a temporary build directory.
     (NO caches, credentials, tokens, or personal config!)
  3. Compiles the Inno Setup script into installer/dist/Tasks_Setup.exe.
  4. Cleans up temporary build files.

Requirements:
  - Inno Setup 6 installed: https://jrsoftware.org/isdl.php
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _rmtree_robust(path: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Robustly deletes a directory tree, handling temporary Windows file locks."""
    def on_error(func, path_item, exc_info):
        try:
            os.chmod(path_item, stat.S_IWRITE)
            func(path_item)
        except Exception:
            pass

    for attempt in range(retries):
        try:
            shutil.rmtree(path, onerror=on_error)
            return
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
    try:
        shutil.rmtree(path, onerror=on_error)
    except Exception as e:
        print(f"   ⚠️  Build directory could not be fully deleted: {e}")
        print(f"      You can manually remove: {path}")


# Paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
INSTALLER_DIR = Path(__file__).parent.resolve()

ISCC_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]

INCLUDE_FILES = [
    "main.py",
    "requirements.txt",
    "run.bat",
    "setup.bat",
    "tasks.bat",
    "tasks.cmd",
]

INCLUDE_DIRS = [
    "assets",
    "scripts",
    "skills",
    "src",
]

NEVER_INCLUDE = {
    "cache",
    "data",
    "config.json",
    "custom_exams.json",
    "deleted_tasks.json",
    "exam_notes.json",
    "custom_tasks.json",
    "__pycache__",
    "installer",
    "dist",
    ".git",
    ".github",
}


def find_iscc() -> str:
    """Finds the Inno Setup Compiler executable."""
    for path in ISCC_PATHS:
        if os.path.exists(path):
            return path
    which_iscc = shutil.which("iscc")
    if which_iscc:
        return which_iscc
    return None


def ensure_python_installer(target_path: Path) -> None:
    """Downloads official Python 3.12 installer on demand if missing."""
    if target_path.exists():
        size_mb = target_path.stat().st_size / (1024 * 1024)
        print(f"  * Python offline installer present ({size_mb:.1f} MB)")
        return

    url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
    print(f"  * Downloading official Python 3.12 installer from {url} ...")
    urllib.request.urlretrieve(url, target_path)
    size_mb = target_path.stat().st_size / (1024 * 1024)
    print(f"  * Downloaded python_installer.exe ({size_mb:.1f} MB)")


def copy_project_files(build_dir: Path) -> None:
    """Copies only clean project files into the temporary build folder."""
    copied = 0

    for filename in INCLUDE_FILES:
        src = PROJECT_ROOT / filename
        if src.exists():
            shutil.copy2(src, build_dir / filename)
            copied += 1
        else:
            print(f"   [!] Warning: Missing expected file: {filename}")

    for dirname in INCLUDE_DIRS:
        src = PROJECT_ROOT / dirname
        dst = build_dir / dirname
        if src.exists():
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.pyo",
                    "*credentials*.json", "*cookies*.json",
                    "teams_browser_profile", "untis_browser_profile",
                ),
            )
            copied += 1
        else:
            print(f"   [!] Warning: Missing expected directory: {dirname}")

    print(f"   * Copied {copied} files/directories into clean build directory")


def build_inno_installer(version: str, output_name: str, build_dir: Path, iscc: str) -> Path:
    """Compiles the Inno Setup script into dist/."""
    iss_template = INSTALLER_DIR / "tasks.iss"
    if not iss_template.exists():
        print(f"ERROR: {iss_template} not found!")
        sys.exit(1)

    iss_content = iss_template.read_text(encoding="utf-8")
    dist_dir = INSTALLER_DIR / "dist"
    dist_dir.mkdir(exist_ok=True)

    defines = (
        f'#define AppVersion "{version}"\n'
        f'#define OutputBaseFilename "{output_name}"\n'
        f'#define SourceDir "{build_dir}"\n'
        f'#define OutputDir "{dist_dir}"\n'
        f'#define InstallerDir "{INSTALLER_DIR}"\n'
    )
    iss_content = defines + iss_content

    temp_iss = INSTALLER_DIR / f"_temp_build_{output_name}.iss"
    temp_iss.write_text(iss_content, encoding="utf-8")

    result = subprocess.run(
        [iscc, str(temp_iss)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    temp_iss.unlink(missing_ok=True)

    if result.stdout:
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("Inno Setup"):
                print(f"   [ISCC] {line}")

    if result.returncode != 0:
        print(f"ERROR: Inno Setup error (Exit Code: {result.returncode})")
        if result.stderr:
            print(result.stderr[-1000:])
        sys.exit(1)

    output_exe = dist_dir / f"{output_name}.exe"
    if not output_exe.exists():
        print(f"ERROR: Output installer EXE not found: {output_exe}")
        sys.exit(1)

    return output_exe


def main():
    parser = argparse.ArgumentParser(
        description="Builds the official open-source Tasks Inno Setup installer."
    )
    parser.add_argument(
        "--version",
        default="2.0.0",
        help="Release version string (e.g. '2.0.0'). Defaults to 2.0.0.",
    )
    parser.add_argument(
        "--output-name",
        default="Tasks_Setup",
        help="Base filename of output installer (without .exe). Defaults to 'Tasks_Setup'.",
    )
    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="Do not delete temporary build directory (for debugging).",
    )
    parser.add_argument(
        "--no-python-download",
        action="store_true",
        help="Skip downloading python_installer.exe if missing.",
    )
    args = parser.parse_args()

    version = args.version.strip().lstrip("v")
    output_name = args.output_name.strip()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "=" * 54)
    print("  Tasks Installer Builder")
    print(f"  Version: {version}")
    print(f"  Output:  {output_name}.exe")
    print("=" * 54 + "\n")

    iscc = find_iscc()
    if not iscc:
        print("ERROR: Inno Setup 6 compiler (ISCC.exe) not found!")
        print("   Install it from: https://jrsoftware.org/isdl.php")
        sys.exit(1)
    print(f"  * Inno Setup found: {iscc}")

    py_installer_path = INSTALLER_DIR / "python_installer.exe"
    if not args.no_python_download:
        ensure_python_installer(py_installer_path)

    build_dir = PROJECT_ROOT / f".build_{output_name}"
    if build_dir.exists():
        _rmtree_robust(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("\n  [1/2] Copying clean project files...")
        copy_project_files(build_dir)

        print(f"\n  [2/2] Compiling {output_name}.exe with Inno Setup...")
        output_exe = build_inno_installer(version, output_name, build_dir, iscc)

        print("\n" + "=" * 54)
        print("  BUILD COMPLETED SUCCESSFULLY!")
        print("=" * 54)
        print(f"\n  Target file: {output_exe}")
        size_mb = output_exe.stat().st_size / (1024 * 1024)
        print(f"  File size:   {size_mb:.1f} MB\n")

    finally:
        if not args.keep_build and build_dir.exists():
            _rmtree_robust(build_dir)
            print("  ✓ Cleaned up temporary build directory.")


if __name__ == "__main__":
    main()
