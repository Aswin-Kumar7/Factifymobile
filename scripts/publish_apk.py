"""Publish the Android app for the website's download page.

Copies the release APK to `downloads/factify.apk` beside `downloads/factify.json`,
which says what the page shows about it: the version (from pubspec.yaml), the size,
the SHA-256 people can check the file against, and the oldest Android it runs on
(from the build's merged manifest). Caddy serves that folder at /downloads
(deploy/Caddyfile); for the dev server, `--web` puts a copy in web/public/downloads.

    uv run python scripts/publish_apk.py            # after `flutter build apk --release`
    uv run python scripts/publish_apk.py --web      # also for `npm run dev`

On the server, copy the folder next to deploy/ (~/factify/downloads); no rebuild
of anything is needed, the page reads factify.json when it opens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "mobile"
DEFAULT_APK = MOBILE / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
MANIFESTS = MOBILE / "build" / "app" / "intermediates" / "merged_manifest" / "release"

# Android's API levels, as people know them.
ANDROID = {21: "5", 22: "5.1", 23: "6", 24: "7", 25: "7.1", 26: "8", 27: "8.1", 28: "9",
           29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14", 35: "15"}  # fmt: skip


def version() -> str:
    text = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([0-9][^\s+]*)", text, re.M)
    return match.group(1) if match else ""


def min_android() -> str:
    for manifest in sorted(MANIFESTS.rglob("AndroidManifest.xml")):
        match = re.search(r'minSdkVersion="(\d+)"', manifest.read_text(encoding="utf-8"))
        if match:
            return ANDROID.get(int(match.group(1)), "")
    return ""


def describe(apk: Path) -> dict[str, str]:
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    size = apk.stat().st_size
    return {
        "version": version(),
        "size": f"{size / 1_000_000:.0f} MB",
        "bytes": str(size),
        "sha256": digest,
        "min_android": min_android(),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def publish(apk: Path, folder: Path) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(apk, folder / "factify.apk")
    facts = describe(folder / "factify.apk")
    (folder / "factify.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    parser.add_argument("--to", type=Path, default=ROOT / "downloads")
    parser.add_argument("--web", action="store_true", help="also into web/public/downloads")
    args = parser.parse_args()
    if not args.apk.exists():
        raise SystemExit(f"no APK at {args.apk}: run `flutter build apk --release` first")
    facts = publish(args.apk, args.to)
    if args.web:
        publish(args.apk, ROOT / "web" / "public" / "downloads")
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
