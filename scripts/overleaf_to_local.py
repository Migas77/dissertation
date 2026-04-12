#!/usr/bin/env python3
"""
Overleaf → Local Sync Script
Downloads a project zip from a self-hosted Overleaf instance
and extracts it into a local directory, overwriting changed files.

Usage:
    python overleaf_sync.py PROJECT_ID SESSION_COOKIE [--host URL] [--path DIR]
"""

import os
import io
import zipfile
import requests
import argparse
from urllib.parse import unquote


def try_download(url, cookie_value, label):
    response = requests.get(
        url,
        headers={"Cookie": f"overleaf.sid={cookie_value}"},
        timeout=60,
        allow_redirects=True,
    )
    content_type = response.headers.get("Content-Type", "")
    is_html = "text/html" in content_type
    print(f"  [{label}] status={response.status_code} type={content_type} size={len(response.content)}")
    if response.status_code == 200 and not is_html:
        return io.BytesIO(response.content)
    return None


def download_zip(url, cookie):
    print(f"Downloading project zip from {url} ...")

    decoded = unquote(cookie)
    encoded = cookie

    # Try decoded cookie first, then raw encoded
    for value, label in [(decoded, "decoded"), (encoded, "raw")]:
        result = try_download(url, value, label)
        if result:
            print(f"  Success with {label} cookie.")
            return result

    # Both failed — show what the server returned for debugging
    response = requests.get(
        url,
        headers={"Cookie": f"overleaf.sid={decoded}"},
        timeout=60,
    )
    print("\nServer returned (first 800 chars):")
    print(response.content[:800].decode("utf-8", errors="replace"))
    raise RuntimeError(
        "Authentication failed. The cookie may have expired or be incorrect.\n"
        "  1. Open your Overleaf in the browser\n"
        "  2. DevTools (F12) → Application → Cookies → http://localhost\n"
        "  3. Find 'overleaf.sid' and copy its Value column (not the URL bar)"
    )


def sync_to_local(zip_bytes, local_path):
    local_path = os.path.abspath(local_path)
    os.makedirs(local_path, exist_ok=True)

    with zipfile.ZipFile(zip_bytes) as zf:
        names = zf.namelist()
        print(f"\nFound {len(names)} files in zip.")

        updated = 0
        skipped = 0

        for name in names:
            if name.endswith("/"):
                continue

            target = os.path.join(local_path, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)

            new_content = zf.read(name)

            if os.path.exists(target):
                with open(target, "rb") as f:
                    existing_content = f.read()
                if existing_content == new_content:
                    skipped += 1
                    continue

            with open(target, "wb") as f:
                f.write(new_content)
            print(f"  Updated: {name}")
            updated += 1

    print(f"\nDone. {updated} file(s) updated, {skipped} file(s) unchanged.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download an Overleaf project zip and sync it to a local directory."
    )
    parser.add_argument("project_id",     help="Overleaf project ID (from the project URL)")
    parser.add_argument("session_cookie", help="Value of the overleaf.sid browser cookie")
    parser.add_argument(
        "--host", default="http://localhost",
        help="Overleaf host URL (default: http://localhost)"
    )
    parser.add_argument(
        "--path", default="./dissertation",
        help="Local directory to sync into (default: ./dissertation)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    zip_url = f"{args.host.rstrip('/')}/project/{args.project_id}/download/zip"

    try:
        zip_bytes = download_zip(zip_url, args.session_cookie)
        sync_to_local(zip_bytes, args.path)
    except RuntimeError as e:
        print(f"\nError: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()