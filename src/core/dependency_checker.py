"""
dependency_checker.py - Lightweight pre-flight dependency checker.
Detects missing project requirements using only the Python standard library.
Displays a clear English warning banner with Windows installation commands
and provides an interactive prompt to install missing dependencies automatically.
"""

import importlib.util
import os
import subprocess
import sys
from typing import List, Tuple

# Mapping of package distribution name -> (import_name, description)
REQUIRED_PACKAGES = {
    "textual": ("textual", "Textual TUI framework"),
    "rich": ("rich", "Terminal formatting & console UI"),
    "requests": ("requests", "HTTP client for Moodle & Untis API"),
    "playwright": ("playwright", "Browser automation for Microsoft Teams"),
    "fpdf2": ("fpdf", "PDF generation for excuse letters"),
    "PyMuPDF": ("pymupdf", "PDF processing & bookmarks for schoolbooks"),
    "Pillow": ("PIL", "Image processing for Digi4School grabber"),
    "pytesseract": ("pytesseract", "OCR engine for searchable schoolbook PDFs"),
}


def get_project_root() -> str:
    """Returns the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # src/core -> src -> project root
    return os.path.abspath(os.path.join(current_dir, "..", ".."))


def get_requirements_txt_path() -> str:
    """Finds the absolute path to requirements.txt in the project root."""
    root = get_project_root()
    return os.path.join(root, "requirements.txt")


def check_missing_requirements() -> List[Tuple[str, str, str]]:
    """
    Checks each required package in REQUIRED_PACKAGES using importlib.util.find_spec.
    Returns a list of tuples: (dist_name, import_name, description) for all missing packages.
    """
    missing = []
    for dist_name, (import_name, desc) in REQUIRED_PACKAGES.items():
        try:
            spec = importlib.util.find_spec(import_name)
            if spec is None and dist_name == "PyMuPDF":
                spec = importlib.util.find_spec("fitz")
            if spec is None:
                missing.append((dist_name, import_name, desc))
        except Exception:
            missing.append((dist_name, import_name, desc))
    return missing


def format_warning_banner(missing: List[Tuple[str, str, str]], install_cmd: str) -> str:
    """Formats an English framed warning banner showing missing requirements and install command."""
    border_len = 78
    title = "[!] WARNING: Missing Required Dependencies"
    pad_left = (border_len - 2 - len(title)) // 2
    pad_right = border_len - 2 - len(title) - pad_left

    lines = [
        "",
        "+" + "-" * (border_len - 2) + "+",
        "|" + " " * pad_left + title + " " * pad_right + "|",
        "+" + "-" * (border_len - 2) + "+",
        "",
        "The following required Python package(s) from requirements.txt are not installed:",
    ]

    for dist_name, _, desc in missing:
        lines.append(f"  * {dist_name:<14} ({desc})")

    lines.extend([
        "",
        "Windows Installation Command:",
        f"  {install_cmd}",
        "",
    ])

    return "\n".join(lines)


def check_playwright_chromium_installed() -> bool:
    """Checks whether Playwright's Chromium browser binary is installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            return bool(exec_path and os.path.exists(exec_path))
    except Exception:
        return False


def install_playwright_chromium() -> int:
    """Installs Playwright's Chromium browser binary."""
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    print(f"\n[INFO] Installing Playwright Chromium browser binary (for Microsoft Teams)...\n" + "-" * 78)
    try:
        res = subprocess.run(cmd)
        return res.returncode
    except Exception as e:
        print(f"\n[ERROR] Failed to install Playwright browser: {e}")
        return 1


def run_pip_install(requirements_path: str) -> int:
    """Runs 'python -m pip install -r requirements.txt' with the current Python executable."""
    cmd = [sys.executable, "-m", "pip", "install", "-r", requirements_path]
    print(f"\n[INFO] Executing: {' '.join(cmd)}\n" + "-" * 78)
    try:
        result = subprocess.run(cmd)
        if result.returncode == 0:
            # Install Playwright browser if not yet present
            if not check_playwright_chromium_installed():
                install_playwright_chromium()
        return result.returncode
    except Exception as e:
        print(f"\n[ERROR] Failed to execute pip command: {e}")
        return 1


def ensure_dependencies(requirements_path: str = None) -> bool:
    """
    Verifies that all required packages are installed.
    If packages are missing:
      - Renders an English warning banner with the Windows install command.
      - If running in an interactive terminal, prompts the user to install them automatically.
      - Proceeds with application launch if installation succeeds, or exits cleanly with code 1.
    """
    missing = check_missing_requirements()
    if not missing:
        return True

    if requirements_path is None:
        requirements_path = get_requirements_txt_path()

    install_cmd = "python -m pip install -r requirements.txt"
    banner = format_warning_banner(missing, install_cmd)
    print(banner, file=sys.stderr)

    is_interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not is_interactive:
        print(
            "[ERROR] Non-interactive environment detected. Please install the missing dependencies manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        prompt_text = "Would you like to install the missing dependencies now? [Y/n]: "
        choice = input(prompt_text).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n\nOperation cancelled by user.")
        sys.exit(1)

    if choice in ("", "y", "yes"):
        print("\nStarting installation...")
        code = run_pip_install(requirements_path)
        if code == 0:
            print("\n" + "-" * 78)
            print("[OK] All dependencies successfully installed! Launching application...\n")
            return True
        else:
            print(
                f"\n[ERROR] Installation failed (exit code {code}).\n"
                f"Please run the command manually:\n  {install_cmd}\n",
                file=sys.stderr,
            )
            sys.exit(code)
    else:
        print(
            "\nInstallation declined.\n"
            "Please install the required packages to run Tasks:\n"
            f"  {install_cmd}\n",
            file=sys.stderr,
        )
        sys.exit(1)
