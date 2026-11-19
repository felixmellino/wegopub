"""Run with python -m data.cleanup_checkin_photos [--apply]."""

import argparse
import sys

from httpx import RequestError
from postgrest.exceptions import APIError
from storage3.utils import StorageException

from data.db import cleanup_checkin_photos


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove expired and abandoned private check-in photos; preserve scores.")
    parser.add_argument("--apply", action="store_true", help="Delete files. Without this option, only count eligible files.")
    args = parser.parse_args()
    try:
        counts = cleanup_checkin_photos(apply=args.apply)
    except (APIError, RequestError, RuntimeError, StorageException):
        print("Photo cleanup failed. Check the server configuration and retry.", file=sys.stderr)
        return 1
    action = "Removed" if args.apply else "Eligible for removal"
    print(f"{action}: {counts['expired']} expired, {counts['unlinked']} unlinked photos. Scores kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
