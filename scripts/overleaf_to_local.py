#!/usr/bin/env python3
"""
Overleaf → Local Sync Script
Downloads a project zip from a self-hosted Overleaf instance
and extracts it into a local directory, overwriting changed files.

Usage:
    python overleaf_sync.py PROJECT_ID SESSION_COOKIE [--host URL] [--path DIR] [--ignore FILE ...]

Examples:
    python overleaf_sync.py PROJECT_ID COOKIE
    python overleaf_sync.py PROJECT_ID COOKIE --ignore miguelf.sty custom-theme.tex
    python overleaf_sync.py PROJECT_ID COOKIE --ignore-file .olignore
"""

import os
import io
import fnmatch
import zipfile
import requests
import argparse
from urllib.parse import unquote

TEXT_EXTENSIONS = {
    ".tex", ".bib", ".sty", ".cls", ".txt", ".md", ".cfg",
    ".ini", ".yaml", ".yml", ".json", ".csv", ".log"
}


def is_text_file(name):
    _, ext = os.path.splitext(name)
    return ext.lower() in TEXT_EXTENSIONS


def normalize_line_endings(content, name):
    """Normalize to Unix line endings for text files."""
    if is_text_file(name):
        return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return content


def load_ignore_patterns(ignore_list, ignore_file):
    patterns = set(ignore_list or [])

    if ignore_file and os.path.exists(ignore_file):
        with open(ignore_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.add(line)

    return patterns


def is_ignored(name, patterns):
    basename = os.path.basename(name.rstrip("/"))
    name_stripped = name.rstrip("/")
    for pattern in patterns:
        pattern_stripped = pattern.rstrip("/")
        if (fnmatch.fnmatch(basename, pattern_stripped) or
                fnmatch.fnmatch(name_stripped, pattern_stripped)):
            return True
    return False


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

    for value, label in [(decoded, "decoded"), (encoded, "raw")]:
        result = try_download(url, value, label)
        if result:
            print(f"  Success with {label} cookie.")
            return result

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


def get_local_files(local_path, ignore_patterns):
    """Walk the local directory, skipping ignored files and directories."""
    local_files = set()
    for dirpath, dirnames, filenames in os.walk(local_path):
        # Prune ignored dirs in-place so os.walk won't descend into them
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(d, ignore_patterns)
        ]
        for filename in filenames:
            if is_ignored(filename, ignore_patterns):
                continue
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, local_path)
            local_files.add(rel_path.replace(os.sep, "/"))
    return local_files


def report_additional_files(local_path, zip_names, ignore_patterns):
    """Print files present locally but not in the Overleaf zip."""
    # Collect non-directory zip entries (normalized)
    overleaf_files = {
        name for name in zip_names if not name.endswith("/")
    }

    local_files = get_local_files(local_path, ignore_patterns)

    additional = sorted(
        f for f in local_files
        if f not in overleaf_files
    )

    YELLOW = "\033[33m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    print()
    print(f"{BOLD}{'─' * 60}{RESET}")
    print(
        f"{BOLD}{YELLOW}Additional Files: files not present in Overleaf project{RESET}\n"
        f"{YELLOW}(possibly useless or outdated){RESET}"
    )
    print(f"{BOLD}{'─' * 60}{RESET}")

    if additional:
        for f in additional:
            print(f"  {YELLOW}?  {f}{RESET}")
    else:
        print("  (none — local directory matches the Overleaf project)")

    print(f"{BOLD}{'─' * 60}{RESET}")


def sync_to_local(zip_bytes, local_path, ignore_patterns):
    local_path = os.path.abspath(local_path)
    os.makedirs(local_path, exist_ok=True)

    if ignore_patterns:
        print(f"Ignoring patterns: {', '.join(sorted(ignore_patterns))}")

    with zipfile.ZipFile(zip_bytes) as zf:
        names = zf.namelist()
        print(f"\nFound {len(names)} files in zip.")

        updated = 0
        skipped = 0
        ignored = 0

        for name in names:
            if name.endswith("/"):
                continue

            if is_ignored(name, ignore_patterns):
                print(f"  Ignored:  {name}")
                ignored += 1
                continue

            target = os.path.join(local_path, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)

            new_content = normalize_line_endings(zf.read(name), name)

            if os.path.exists(target):
                with open(target, "rb") as f:
                    existing_content = normalize_line_endings(f.read(), name)
                if existing_content == new_content:
                    skipped += 1
                    continue

            with open(target, "wb") as f:
                f.write(new_content)
            print(f"  Updated:  {name}")
            updated += 1

        print(f"\nDone. {updated} file(s) updated, {skipped} unchanged, {ignored} ignored.")

        report_additional_files(local_path, names, ignore_patterns)


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
        "--path", default="./",
        help="Local directory to sync into (default: ./)"
    )
    parser.add_argument(
        "--ignore", nargs="+", metavar="PATTERN", default=['Makefile', 'scripts/*.py', '.git/', '.gitignore'],
        help="Filenames or patterns to skip (e.g. --ignore *.bak)"
    )
    parser.add_argument(
        "--ignore-file", metavar="FILE", default=".olignore",
        help="Path to a file with ignore patterns, one per line (default: .olignore)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    zip_url = f"{args.host.rstrip('/')}/project/{args.project_id}/download/zip"
    ignore_patterns = load_ignore_patterns(args.ignore, args.ignore_file)

    try:
        zip_bytes = download_zip(zip_url, args.session_cookie)
        sync_to_local(zip_bytes, args.path, ignore_patterns)
    except RuntimeError as e:
        print(f"\nError: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()