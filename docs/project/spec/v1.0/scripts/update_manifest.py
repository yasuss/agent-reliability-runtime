"""Generate manifest only from already staged Git index payload blobs."""

import argparse
import hashlib
from pathlib import Path

from validate_spec import CHECKSUM, MANIFEST, PREFIX, manifest_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[5]
    )
    args = parser.parse_args()
    raw = manifest_bytes(args.root, "index")
    directory = args.root / PREFIX
    (directory / MANIFEST).write_bytes(raw)
    (directory / CHECKSUM).write_bytes(
        (hashlib.sha256(raw).hexdigest() + "  " + MANIFEST + "\n").encode("ascii")
    )
    print(
        "Manifest generated from staged Git index blobs; "
        "stage manifest and validate --source index"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
