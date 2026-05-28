#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
from urllib.parse import quote


REAL_2026_01 = [
    "2026.01_Enamine_REAL_HAC_29_38_2.9B_Part_2_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_29_38_2.9B_Part_1_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_28_1.6B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_27_1.8B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_26_1.7B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_25_1.6B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_24_1.3B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_22_23_1.6B_CXSMILES.cxsmiles.bz2",
    "2026.01_Enamine_REAL_HAC_11_21_1.2B_CXSMILES.cxsmiles.bz2",
]


class EnamineRealDownloader:
    login_url = "https://enamine.net/compound-collections/real-compounds/real-database"
    download_root = "https://ftp.enamine.net/download/REAL"

    def __init__(self, username: str, password: str) -> None:
        try:
            import requests
        except ImportError as exc:
            raise SystemExit("This downloader requires requests. Install backend requirements with: pip install -r backend/requirements.txt") from exc

        self.session = requests.Session()
        response = self.session.get(
            self.login_url,
            params={
                "username": username,
                "password": password,
                "Submit": "Login",
                "remember": "yes",
                "option": "com_users",
                "task": "user.login",
            },
            timeout=60,
        )
        response.raise_for_status()

    def check(self, filename: str) -> None:
        url = self._url(filename)
        with self.session.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            next(response.iter_content(chunk_size=8192), b"")

    def download(self, filename: str, output_dir: Path, overwrite: bool = False) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        if output_path.exists() and not overwrite:
            print(f"skip existing: {output_path}")
            return output_path

        temp_path = output_path.with_suffix(output_path.suffix + ".part")
        url = self._url(filename)
        print(f"downloading {url}")
        with self.session.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temp_path.replace(output_path)
        print(f"saved {output_path}")
        return output_path

    def _url(self, filename: str) -> str:
        return f"{self.download_root}/{quote(filename)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Enamine REAL CXSMILES files using an Enamine account.")
    parser.add_argument("--output-dir", default="backend/data/enamine_real", help="Directory for downloaded REAL files.")
    parser.add_argument("--file", action="append", dest="files", help="Specific REAL filename to download. Can be repeated.")
    parser.add_argument("--all", action="store_true", help="Download every known 2026.01 REAL file.")
    parser.add_argument("--check", action="store_true", help="Check that selected files are accessible without downloading them.")
    parser.add_argument("--list", action="store_true", help="List known 2026.01 REAL files and exit.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args()

    if args.list:
        for filename in REAL_2026_01:
            print(filename)
        return

    files = args.files or []
    if args.all:
        files = REAL_2026_01
    if not files:
        raise SystemExit("Select --all or at least one --file. Use --list to see known files.")

    username = os.environ.get("ENAMINE_USERNAME") or input("Enamine username: ").strip()
    password = os.environ.get("ENAMINE_PASSWORD") or getpass.getpass("Enamine password: ")
    downloader = EnamineRealDownloader(username=username, password=password)

    output_dir = Path(args.output_dir)
    for filename in files:
        if args.check:
            downloader.check(filename)
            print(f"ok: {filename}")
        else:
            downloader.download(filename, output_dir=output_dir, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
