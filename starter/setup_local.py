"""Download pinned official assets, verify SHA-256, and safely extract.

No pip packages, shell installation scripts, administrative installation, or
trust_remote_code. Windows x64 automatic setup; other hosts can supply paths.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "starter/local_config.json").read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, path, expected):
    if path.exists() and sha256(path) == expected:
        print(f"Verified existing {path.name}", flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".tmp")
    print(f"Downloading {path.name} from {url}", flush=True)
    try:
        with urlopen(Request(url, headers={"User-Agent": "UnderAI-assignment/1.0"}), timeout=120) as response:
            with partial.open("wb") as stream:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(chunk)
        if sha256(partial) != expected:
            raise ValueError(f"SHA-256 mismatch: {path.name}")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def setup():
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Automatic setup supports Windows x64. See README for other systems.")
    archive = ROOT / ".runtime" / CONFIG["windows_archive"]
    download(f"https://github.com/ggml-org/llama.cpp/releases/download/{CONFIG['llama_version']}/{archive.name}",
             archive, CONFIG["windows_archive_sha256"])
    destination = ROOT / ".runtime" / CONFIG["llama_version"]
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe archive path")
        bundle.extractall(destination)
    model = ROOT / ".models" / CONFIG["file"]
    download(f"https://huggingface.co/{CONFIG['model']}/resolve/{CONFIG['revision']}/{model.name}",
             model, CONFIG["model_sha256"])
    print("Local assets ready. Run python starter/run.py --mode local", flush=True)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    setup()
