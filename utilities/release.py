#!/usr/bin/env python3
"""
Stamp the Unreleased section in CHANGELOG.md with a new version, commit, and tag.

Usage:
    python utilities/release.py 0.2.0
    make release VERSION=0.2.0
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
GITHUB_REPO = "marcinstopyra/polyglot-pigeon"
BASE_URL = f"https://github.com/{GITHUB_REPO}"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: release.py <version>  (e.g. 0.2.0)")
        sys.exit(1)

    version = sys.argv[1].lstrip("v")
    tag = f"v{version}"
    today = date.today().isoformat()

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"Error: version must be x.y.z format, got '{version}'")
        sys.exit(1)

    text = CHANGELOG.read_text()

    if "## [Unreleased]" not in text:
        print("Error: no [Unreleased] section found in CHANGELOG.md")
        sys.exit(1)

    if f"## [{version}]" in text:
        print(f"Error: {version} already exists in CHANGELOG.md")
        sys.exit(1)

    # Stamp [Unreleased] → [Unreleased] + new version heading
    text = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{version}] - {today}",
        1,
    )

    # Find the previous latest tag from the [Unreleased] comparison link
    prev_tag_match = re.search(r"\[Unreleased\]: .+/compare/(.+)\.\.\.HEAD", text)
    prev_tag = prev_tag_match.group(1) if prev_tag_match else None

    # Update [Unreleased] comparison link to point from new tag
    text = re.sub(
        r"\[Unreleased\]: .+",
        f"[Unreleased]: {BASE_URL}/compare/{tag}...HEAD",
        text,
    )

    # Insert new version link directly after the [Unreleased] link
    if prev_tag:
        new_link = f"[{version}]: {BASE_URL}/compare/{prev_tag}...{tag}"
    else:
        new_link = f"[{version}]: {BASE_URL}/releases/tag/{tag}"

    text = re.sub(
        r"(\[Unreleased\]: .+\n)",
        f"\\1{new_link}\n",
        text,
        count=1,
    )

    CHANGELOG.write_text(text)
    print(f"Updated CHANGELOG.md — stamped [{version}] - {today}")

    run(["git", "add", str(CHANGELOG)])
    run(["git", "commit", "-m", f"Release {tag}"])
    run(["git", "tag", tag])

    print(f"Created commit and tag {tag}")
    print(f"\nTo publish:")
    print(f"  git push && git push origin {tag}")


if __name__ == "__main__":
    main()
