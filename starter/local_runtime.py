"""Own a loopback-only llama.cpp process for the duration of one CLI run."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError, HTTPError
from urllib.request import build_opener, ProxyHandler

from setup_local import CONFIG, ROOT, sha256


@contextmanager
def local_server():
    model = Path(os.environ.get("UNDERAI_MODEL_PATH", ROOT / ".models" / CONFIG["file"]))
    configured = os.environ.get("UNDERAI_LLAMA_SERVER")
    servers = list((ROOT / ".runtime" / CONFIG["llama_version"]).rglob("llama-server.exe"))
    executable = Path(configured) if configured else (servers[0] if servers else None)
    if executable is None or not executable.is_file() or not model.is_file():
        raise RuntimeError("Local assets missing. Run python starter/setup_local.py or set UNDERAI_LLAMA_SERVER and UNDERAI_MODEL_PATH.")
    if sha256(model) != CONFIG["model_sha256"]:
        raise ValueError("Local model checksum differs from the pinned Qwen snapshot")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [str(executable.resolve()), "--model", str(model.resolve()), "--host", "127.0.0.1",
               "--port", str(port), "--ctx-size", str(CONFIG["context_size"]),
               "--threads", str(CONFIG["threads"]), "--parallel", "1", "--n-gpu-layers", "0",
               "--jinja", "--alias", CONFIG["model"], "--no-webui"]
    log_path = ROOT / ".runtime/server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, creationflags=flags)
        try:
            opener = build_opener(ProxyHandler({}))
            while time.perf_counter() - started < 120:
                if process.poll() is not None:
                    raise RuntimeError(f"llama-server exited ({process.returncode}); see {log_path}")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        if json.load(response).get("status") == "ok":
                            break
                except (URLError, HTTPError, TimeoutError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local model startup timed out")
            yield f"http://127.0.0.1:{port}/v1", {
                **CONFIG, "server_command": [Path(command[0]).name, "--model", CONFIG["file"], *command[3:]],
                "startup_seconds": round(time.perf_counter() - started, 3),
                "runtime_version": subprocess.check_output([str(executable.resolve()), "--version"],
                    stderr=subprocess.STDOUT, text=True, creationflags=flags).strip(),
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
