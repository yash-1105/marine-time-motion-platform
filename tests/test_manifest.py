import hashlib
import json
from pathlib import Path


def test_manifest_checksum():
    manifest_path = Path("fixtures/MANIFEST.json")
    assert manifest_path.exists()

    with open(manifest_path) as f:
        manifest = json.load(f)

    excel_path = Path("fixtures") / manifest["filename"]
    assert excel_path.exists()

    with open(excel_path, "rb") as f:
        data = f.read()

    sha256 = hashlib.sha256(data).hexdigest()
    assert sha256 == manifest["sha256"]
    assert manifest["synthetic"] is True
