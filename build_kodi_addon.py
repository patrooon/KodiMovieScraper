"""Build a Kodi-installable addon zip from the project sources."""

from __future__ import annotations

import shutil
from pathlib import Path

ADDON_ID = "script.kodimoviescraper"
PROJECT_ROOT = Path(__file__).resolve().parent
BUILD_ROOT = PROJECT_ROOT / "build"
PACKAGE_ROOT = BUILD_ROOT / ADDON_ID
ZIP_PATH = BUILD_ROOT / f"{ADDON_ID}.zip"


def copy_tree(source: Path, destination: Path) -> None:
    """Copy a source directory into the addon package directory."""
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def main() -> None:
    """Create a Kodi-ready addon zip under the build directory."""
    if PACKAGE_ROOT.exists():
        shutil.rmtree(PACKAGE_ROOT)
    ZIP_PATH.unlink(missing_ok=True)
    PACKAGE_ROOT.mkdir(parents=True)

    shutil.copy2(PROJECT_ROOT / "addon" / "addon.xml", PACKAGE_ROOT / "addon.xml")
    shutil.copy2(PROJECT_ROOT / "addon" / "default.py", PACKAGE_ROOT / "default.py")
    copy_tree(PROJECT_ROOT / "database", PACKAGE_ROOT / "database")
    copy_tree(PROJECT_ROOT / "wiki_page_request", PACKAGE_ROOT / "wiki_page_request")

    archive_base = BUILD_ROOT / ADDON_ID
    shutil.make_archive(str(archive_base), "zip", BUILD_ROOT, ADDON_ID)
    print(f"Created {ZIP_PATH}")


if __name__ == "__main__":
    main()
