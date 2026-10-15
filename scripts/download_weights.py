#!/usr/bin/env python
"""Fetch the FootScan model weights and verify them against FootScan_AI_Core/WEIGHTS.sha256.

The checkpoints are tracked with Git LFS. If you cannot use LFS (e.g. an air-gapped build, or the
repo's LFS bandwidth quota is exhausted), host the files anywhere you control (a GitHub Release
asset, S3, an internal artifact store) and download them with this script:

    python scripts/download_weights.py --url https://example.org/footscan_best_model.pth
    FOOTSCAN_WEIGHTS_URL=https://example.org/footscan_best_model.pth python scripts/download_weights.py

Only https:// URLs are accepted. The file is written to a temporary path, its SHA-256 is checked
against the pinned value, and only then moved into place. A mismatch aborts without installing it.
Use --verify-only to check files that are already on disk (e.g. after `git lfs pull`).
"""

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "FootScan_AI_Core"
CHECKSUM_FILE = CORE_DIR / "WEIGHTS.sha256"
DEFAULT_NAME = "footscan_best_model.pth"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"


def load_checksums() -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in CHECKSUM_FILE.read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[name.lstrip("*").strip()] = digest.lower()
    return sums


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX


def verify(name: str) -> bool:
    path = CORE_DIR / name
    expected = load_checksums().get(name)
    if expected is None:
        print(f"error: {name} has no entry in {CHECKSUM_FILE.name}", file=sys.stderr)
        return False
    if not path.is_file():
        print(f"MISSING  {name}")
        return False
    if is_lfs_pointer(path):
        print(f"POINTER  {name} is a Git LFS pointer; run `git lfs pull` or use --url")
        return False
    actual = sha256_of(path)
    ok = actual == expected
    print(f"{'OK      ' if ok else 'MISMATCH'} {name}")
    return ok


def download(url: str, name: str) -> bool:
    if not url.lower().startswith("https://"):
        print("error: only https:// URLs are accepted", file=sys.stderr)
        return False
    expected = load_checksums().get(name)
    if expected is None:
        print(f"error: {name} has no entry in {CHECKSUM_FILE.name}", file=sys.stderr)
        return False

    CORE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=CORE_DIR, suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - https enforced above
            while chunk := resp.read(1024 * 1024):
                out.write(chunk)
        actual = sha256_of(tmp)
        if actual != expected:
            print(f"error: checksum mismatch for {name}; refusing to install it", file=sys.stderr)
            return False
        tmp.replace(CORE_DIR / name)
        print(f"downloaded and verified {name}")
        return True
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("FOOTSCAN_WEIGHTS_URL"), help="https URL of the weights file")
    parser.add_argument("--name", default=DEFAULT_NAME, help=f"file name to install (default: {DEFAULT_NAME})")
    parser.add_argument("--verify-only", action="store_true", help="only check the files already on disk")
    args = parser.parse_args()

    if args.verify_only:
        return 0 if all(verify(name) for name in load_checksums()) else 1
    if not args.url:
        parser.error("provide --url (or set FOOTSCAN_WEIGHTS_URL), or use --verify-only")
    return 0 if download(args.url, args.name) else 1


if __name__ == "__main__":
    raise SystemExit(main())
