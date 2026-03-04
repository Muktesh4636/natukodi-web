#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re


def main() -> int:
    path = Path("/etc/nginx/sites-available/dice_game")
    s = path.read_text()

    new_upstream = (
        "upstream backend_servers {\n"
        "    least_conn;\n"
        "    server 127.0.0.1:8001 max_fails=5 fail_timeout=30s;\n"
        "    keepalive 256;\n"
        "}\n\n"
    )

    # Replace the first upstream backend_servers {...}\n\n block.
    s2, n = re.subn(
        r"upstream backend_servers \{.*?\}\n\n",
        new_upstream,
        s,
        count=1,
        flags=re.S,
    )

    if n == 0:
        raise SystemExit("Could not find upstream backend_servers block to replace")

    changed = s2 != s
    if changed:
        path.write_text(s2)
        print("patched")
    else:
        print("no_change")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

