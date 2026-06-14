"""
PyInstaller Packaging script for the UX/UI Audit Agent.

Detects platform path separators, bundles the Python modules, PyInstaller hooks,
and PySide6 assets into a standalone installable application folder.
After PyInstaller compilation, generates a native macOS .pkg installer package.
"""

import os
import shutil
import subprocess
import sys


def build_pkg_installer(current_dir: str) -> None:
    """Generates a native macOS .pkg installer with a post-install hook for global symlinking."""
    if sys.platform != "darwin":
        return

    print("\nGenerating native macOS PKG installer...")
    src_app = os.path.join(current_dir, "dist", "UX Audit Agent.app")
    output_pkg = os.path.join(current_dir, "dist", "UX_Audit_Agent_Installer.pkg")
    scripts_dir = os.path.join(current_dir, "build", "pkg_scripts")
    postinstall_script = os.path.join(scripts_dir, "postinstall")

    if not os.path.exists(src_app):
        print(f"Error: Compiled app bundle not found at {src_app}", file=sys.stderr)
        return

    payload_dir = os.path.join(current_dir, "build", "payload")
    try:
        # Create scripts and payload directories
        os.makedirs(scripts_dir, exist_ok=True)
        if os.path.exists(payload_dir):
            shutil.rmtree(payload_dir, ignore_errors=True)
        os.makedirs(payload_dir, exist_ok=True)

        # Copy the app bundle to staging payload directory
        shutil.copytree(src_app, os.path.join(payload_dir, "UX Audit Agent.app"), symlinks=True)

        # Write postinstall script
        # This script runs with administrative privileges inside the macOS Installer session
        script_content = """#!/bin/bash
echo "Setting up global terminal command line tool..."
mkdir -p /usr/local/bin
ln -sf "/Applications/UX Audit Agent.app/Contents/MacOS/UX Audit Agent" /usr/local/bin/ux-audit
chmod +x "/Applications/UX Audit Agent.app/Contents/MacOS/UX Audit Agent"
echo "UX Audit Agent terminal configuration completed successfully."
exit 0
"""
        with open(postinstall_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Make postinstall script executable
        os.chmod(postinstall_script, 0o755)

        # Generate the component plist to disable macOS App Relocation
        import re
        plist_path = os.path.join(current_dir, "build", "component.plist")
        analyze_cmd = [
            "pkgbuild",
            "--analyze",
            "--root", payload_dir,
            plist_path
        ]
        print(f"Analyzing component: {' '.join(analyze_cmd)}")
        subprocess.run(analyze_cmd, check=True)

        with open(plist_path, "r", encoding="utf-8") as f:
            plist_content = f.read()

        # Disable relocation by changing BundleIsRelocatable from true to false
        plist_content = re.sub(
            r"<key>BundleIsRelocatable</key>\s*<true\s*/>",
            "<key>BundleIsRelocatable</key>\n\t\t<false/>",
            plist_content
        )

        with open(plist_path, "w", encoding="utf-8") as f:
            f.write(plist_content)

        # Build PKG installer using macOS native pkgbuild with component plist
        cmd = [
            "pkgbuild",
            "--identifier", "com.uxaudit.agent",
            "--version", "1.0.0",
            "--root", payload_dir,
            "--install-location", "/Applications",
            "--component-plist", plist_path,
            "--scripts", scripts_dir,
            output_pkg
        ]

        print(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        print("\n" + "=" * 60)
        print("INSTALLER GENERATED SUCCESSFULLY!")
        print(f"Double-click to install: dist/UX_Audit_Agent_Installer.pkg")
        print("=" * 60 + "\n")

    except Exception as err:
        print(f"\nError generating PKG installer: {err}", file=sys.stderr)
    finally:
        # Clean up temporary scripts and payload
        if os.path.exists(scripts_dir):
            shutil.rmtree(scripts_dir, ignore_errors=True)
        if os.path.exists(payload_dir):
            shutil.rmtree(payload_dir, ignore_errors=True)


def main() -> None:
    print("Preparing PyInstaller packaging for UX Audit Agent...")

    # Define absolute paths to prevent resolution failures during compilation
    current_dir = os.path.dirname(os.path.abspath(__file__))
    entrypoint = os.path.join(current_dir, "src", "main.py")

    # Locate pyinstaller in the same folder as the python executable running this script
    pyinstaller_bin = os.path.join(os.path.dirname(sys.executable), "pyinstaller")
    if not os.path.exists(pyinstaller_bin):
        pyinstaller_bin = "pyinstaller"

    icon_path = os.path.join(current_dir, "icon.png")

    # Build pyinstaller command line
    cmd = [
        pyinstaller_bin,
        "--name=UX Audit Agent",
        "--noconfirm",               # Overwrite output directory without confirmation
        "--onedir",                  # Bundle as directory (allows easier inspection and deployment)
        "--windowed",                # Hide CLI console window when starting the GUI app
        f"--icon={icon_path}",       # Custom application icon (automatically converted on macOS)
        "--collect-all=google.antigravity",  # Ensure all SDK modules and hooks are fully bundled
        "--collect-all=markdown",    # Ensure markdown parser package is fully collected
        "--clean",
        entrypoint
    ]

    print(f"\nExecuting: {' '.join(cmd)}\n")

    try:
        # Run PyInstaller via subprocess using the virtualenv's pyinstaller binary
        subprocess.run(cmd, check=True)
        print("\n" + "=" * 60)
        print("PACKAGING COMPLETED SUCCESSFULLY!")
        print("The standalone app is built in: dist/UX Audit Agent/")
        print("=" * 60 + "\n")
        
        # Run macOS PKG installer generator post-build step
        build_pkg_installer(current_dir)
        
    except subprocess.CalledProcessError as err:
        print(f"\nError: PyInstaller packaging failed with exit code {err.returncode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
