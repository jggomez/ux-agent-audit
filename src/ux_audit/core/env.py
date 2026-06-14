"""
Environment utility for loading shell configuration on macOS.
Ensures NVM, Node, and Homebrew paths are in the PATH variable
when run under a windowed GUI subprocess.
"""

import os
import sys
import logging
import subprocess

logger = logging.getLogger(__name__)

def _ensure_fallback_paths() -> None:
    """Manually checks and adds standard Homebrew and NVM node version bins to PATH."""
    path_env = os.environ.get("PATH", "")
    paths = path_env.split(os.pathsep)
    
    # Common locations
    extra_paths = ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin"]
    
    # NVM node versions directories
    home = os.path.expanduser("~")
    nvm_dir = os.path.join(home, ".nvm", "versions", "node")
    if os.path.isdir(nvm_dir):
        try:
            for version in os.listdir(nvm_dir):
                version_bin = os.path.join(nvm_dir, version, "bin")
                if os.path.isdir(version_bin) and version_bin not in paths:
                    extra_paths.append(version_bin)
        except Exception as exc:
            logger.debug("Failed scanning NVM dir: %s", exc)

    updated_paths = []
    for p in extra_paths:
        if p not in paths and os.path.exists(p):
            updated_paths.append(p)
            
    if updated_paths:
        os.environ["PATH"] = path_env + os.pathsep + os.pathsep.join(updated_paths)
        logger.info("Fallback environment path resolver added: %s", updated_paths)


def setup_environment() -> None:
    """
    Main environment setup entry point.
    Runs a login shell command to capture user environment variables (PATH, NVM_DIR, etc.)
    and merges them into os.environ.
    """
    if sys.platform != "darwin":
        return

    # Check if we are running from a desktop container (restricted path)
    # or if npx is not found in the path.
    # Finder launch usually results in a path like '/usr/bin:/bin:/usr/sbin:/sbin'
    path_env = os.environ.get("PATH", "")
    if len(path_env.split(os.pathsep)) <= 5 or "npx" not in path_env:
        logger.info("Restricted macOS GUI path detected. Capturing login shell env...")
        try:
            # -l makes it a login shell (executes .zprofile, .zshrc)
            # -c runs env
            result = subprocess.run(
                ["/bin/zsh", "-l", "-c", "env"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True
            )
            
            merged_keys = []
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key in ("PATH", "NVM_DIR", "NODE_PATH", "GEMINI_API_KEY"):
                        if key == "PATH":
                            current_paths = os.environ.get("PATH", "").split(os.pathsep)
                            new_paths = val.split(os.pathsep)
                            merged = []
                            for p in new_paths + current_paths:
                                if p and p not in merged:
                                    merged.append(p)
                            os.environ["PATH"] = os.pathsep.join(merged)
                        else:
                            if val:
                                os.environ[key] = val
                        merged_keys.append(key)
            logger.info("Successfully loaded login shell env keys: %s", merged_keys)
        except Exception as exc:
            logger.warning("Failed to load environment from login shell: %s", exc)

    # Always ensure fallback paths (like NVM version directories) are present
    _ensure_fallback_paths()
