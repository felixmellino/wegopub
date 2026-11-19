"""Run with python -m data.cleanup_profile_pictures [--apply]."""
import argparse
import sys
from httpx import RequestError
from postgrest.exceptions import APIError
from storage3.utils import StorageException
from data.db import cleanup_profile_pictures


def main():
    parser = argparse.ArgumentParser(description='Remove unlinked profile pictures older than 24 hours.')
    parser.add_argument('--apply', action='store_true', help='Delete files; otherwise report only.')
    args = parser.parse_args()
    try:
        count = cleanup_profile_pictures(apply=args.apply)
    except (APIError, RequestError, RuntimeError, StorageException):
        print('Profile picture cleanup failed. Check configuration and retry.', file=sys.stderr)
        return 1
    print(f"{'Removed' if args.apply else 'Eligible for removal'}: {count} unlinked profile pictures.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
