"""Real LoopX Chat service on a fresh runtime: no registry, Goal, model or credential exists.

The scan root is an empty project directory, exactly the state an installed
LoopX opens for the first time; nothing here is synthetic except the browser.
"""
import json
import os
import signal
import socket
import sys
from pathlib import Path

from loopx.chat_server import default_chat_assets_dir, serve_chat

root = Path(sys.argv[1]).resolve()
(root / "project").mkdir(parents=True, exist_ok=True)
os.environ["LOOPX_USAGE_PING"] = "0"
os.environ["DO_NOT_TRACK"] = "1"
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
print(json.dumps({"port": port, "project": str(root / "project")}), flush=True)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
serve_chat(
    registry_path=root / "project" / ".loopx" / "registry.json",
    runtime_root_override=str(root / "runtime"),
    scan_roots=[root / "project"],
    host="127.0.0.1",
    port=port,
    assets_dir=default_chat_assets_dir(),
    open_browser=False,
)
