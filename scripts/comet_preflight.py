from __future__ import annotations

import argparse
import shutil
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--expect-tesseract", action="store_true")
    args = parser.parse_args()

    print(f"Comet target: {args.host}")
    print("Live device actions are intentionally not performed by this script.")

    tesseract = shutil.which("tesseract")
    if args.expect_tesseract and not tesseract:
        print("FAIL: tesseract is not on PATH. Install it or set TESSERACT_PATH for the MCP server.")
        return 2
    if tesseract:
        print(f"Tesseract: {tesseract}")
    else:
        print("Tesseract: not found")

    print("PASS: local preflight complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
