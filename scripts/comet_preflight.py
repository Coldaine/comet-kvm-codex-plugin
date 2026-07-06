from __future__ import annotations

import argparse
import os
import shutil
import sys


def configured_tesseract() -> tuple[str, str]:
    for name in ("TESSERACT_PATH", "TESSERACT_CMD"):
        value = os.environ.get(name)
        if value and os.path.isfile(value):
            return name, value

    value = shutil.which("tesseract")
    if value:
        return "PATH", value

    if os.name == "nt":
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.isfile(candidate):
                return "Windows default path", candidate
    return "", ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--expect-tesseract", action="store_true")
    args = parser.parse_args()

    print(f"Comet target: {args.host}")
    print("Live device actions are intentionally not performed by this script.")

    tesseract_source, tesseract_value = configured_tesseract()
    if args.expect_tesseract and not tesseract_value:
        print("FAIL: tesseract was not found. Install it or set TESSERACT_PATH/TESSERACT_CMD for the MCP server.")
        return 2
    if tesseract_value:
        print(f"Tesseract: {tesseract_source}={tesseract_value}")
    else:
        print("Tesseract: not found")

    print("PASS: local preflight complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
