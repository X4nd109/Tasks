#!/usr/bin/env python
"""
build_exe.py - Builds standalone Tasks.exe and TasksTray.exe using PyInstaller.

Outputs:
  dist/Tasks/
    ├── Tasks.exe        (Console TUI & CLI application)
    ├── TasksTray.exe    (Windowed background tray application)
    ├── _internal/       (Compiled modules, Python runtime, DLLs)
    ├── assets/          (Icons and fonts)
    └── tasks.cmd        (Terminal launcher script)
"""

import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def build() -> int:
    os.chdir(PROJECT_ROOT)
    print("=" * 60)
    print("  Building Tasks Standalone Binaries (PyInstaller)")
    print("=" * 60)

    # 1. Verify PyInstaller availability
    try:
        import PyInstaller
        print(f"[*] Found PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[!] PyInstaller is not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0.0"])

    # 2. Run PyInstaller
    spec_file = os.path.join(PROJECT_ROOT, "tasks.spec")
    if not os.path.exists(spec_file):
        print(f"[X] Spec file not found: {spec_file}")
        return 1

    dist_dir = os.path.join(PROJECT_ROOT, "dist", "Tasks")
    if os.path.exists(dist_dir):
        print("[*] Cleaning existing dist/Tasks directory...")
        import stat

        def _handle_readonly(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        for _ in range(5):
            shutil.rmtree(dist_dir, onerror=_handle_readonly)
            if not os.path.exists(dist_dir):
                break
            import time
            time.sleep(0.5)

    import tempfile
    work_dir = os.path.join(tempfile.gettempdir(), "tasks_pyi_build")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        spec_file,
        "--noconfirm",
        "--clean",
        "--workpath",
        work_dir,
    ]
    print(f"[*] Executing: {' '.join(cmd)}")
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"[X] PyInstaller failed with exit code {ret}")
        return ret

    dist_dir = os.path.join(PROJECT_ROOT, "dist", "Tasks")
    tasks_exe = os.path.join(dist_dir, "Tasks.exe")
    tray_exe = os.path.join(dist_dir, "TasksTray.exe")

    if not (os.path.isfile(tasks_exe) and os.path.isfile(tray_exe)):
        print("[X] Build output executables missing in dist/Tasks/")
        return 1

    # 3. Copy helper scripts and clean up extraneous assets
    print("[*] Packaging runtime helper files...")

    # tasks.cmd
    tasks_cmd_path = os.path.join(dist_dir, "tasks.cmd")
    with open(tasks_cmd_path, "w", encoding="utf-8") as f:
        f.write('@echo off\n"%~dp0Tasks.exe" %*\n')

    # update.bat (standalone updater & repair tool)
    src_update_bat = os.path.join(PROJECT_ROOT, "update.bat")
    if os.path.isfile(src_update_bat):
        shutil.copy2(src_update_bat, os.path.join(dist_dir, "update.bat"))
        print("[*] Copied update.bat (standalone updater & repair tool)")
    else:
        print("[!] Warning: update.bat not found in project root - skipping")

    # scripts: update_launcher.ps1 + Windows Terminal profile helpers
    target_scripts = os.path.join(dist_dir, "scripts")
    os.makedirs(target_scripts, exist_ok=True)
    src_launcher = os.path.join(PROJECT_ROOT, "scripts", "update_launcher.ps1")
    if os.path.isfile(src_launcher):
        shutil.copy2(src_launcher, os.path.join(target_scripts, "update_launcher.ps1"))
    scripts_src_dir = os.path.join(PROJECT_ROOT, "scripts")
    if os.path.isdir(scripts_src_dir):
        for helper_name in sorted(f for f in os.listdir(scripts_src_dir) if f.endswith(".bat")):
            helper_src = os.path.join(scripts_src_dir, helper_name)
            if os.path.isfile(helper_src):
                shutil.copy2(helper_src, os.path.join(target_scripts, helper_name))
                print(f"[*] Copied runtime helper script: {helper_name}")
            else:
                print(f"[!] Missing runtime helper script: {helper_name}")

    # Copy top-level assets (icons)
    target_assets = os.path.join(dist_dir, "assets")
    os.makedirs(target_assets, exist_ok=True)
    for icon_name in ["app_icon.ico", "app_icon.png"]:
        src_icon = os.path.join(PROJECT_ROOT, "assets", icon_name)
        if os.path.isfile(src_icon):
            shutil.copy2(src_icon, os.path.join(target_assets, icon_name))


    # Strip large tutorial screenshots from dist to keep installation lean
    tutorial_dir = os.path.join(dist_dir, "assets", "git-sync-tutorial")
    if os.path.isdir(tutorial_dir):
        shutil.rmtree(tutorial_dir, ignore_errors=True)

    internal_tutorial = os.path.join(dist_dir, "_internal", "assets", "git-sync-tutorial")
    if os.path.isdir(internal_tutorial):
        shutil.rmtree(internal_tutorial, ignore_errors=True)


    print("\n" + "=" * 60)
    print("  [OK] Build Successful!")
    print(f"  Console Binary:    {tasks_exe}")
    print(f"  Background Binary: {tray_exe}")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(build())
