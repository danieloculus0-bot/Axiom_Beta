"""Run Axiom and selected installed companion applications as one local session.

This launcher does not clone code, install packages, share application databases,
or expose an HTTP process-control endpoint. Only a trusted local JSON file
defines optional child commands. Use one port per independent service.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "workspace.modules.example.json"
AXIOM_PORT = 5060


def load_config(config_path: Path) -> list[dict]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("modules"), list):
        raise ValueError("Expected a JSON object with a modules array")
    modules, names = [], set()
    for item in payload["modules"]:
        if not isinstance(item, dict):
            raise ValueError("Each module must be an object")
        key = item.get("id")
        if not isinstance(key, str) or not key or key in names:
            raise ValueError("Module IDs must be distinct nonempty strings")
        names.add(key)
        command = item.get("command")
        if not isinstance(command, list) or not command or any(
            not isinstance(piece, str) or not piece for piece in command
        ):
            raise ValueError(f"{key}: command must be a nonempty string array")
        if not isinstance(item.get("directory"), str):
            raise ValueError(f"{key}: directory must be a path")
        port = item.get("port")
        if port is not None and (type(port) is not int or not 1 <= port <= 65535):
            raise ValueError(f"{key}: invalid local port")
        if item.get("env") is not None and not (
            isinstance(item["env"], dict) and
            all(isinstance(k, str) and isinstance(v, str)
                for k, v in item["env"].items())
        ):
            raise ValueError(f"{key}: env must map names to strings")
        modules.append(item)
    return modules


def busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def plan_modules(config_path: Path, *, all_installed: bool = False) -> list[dict]:
    plan = []
    assigned_ports = {AXIOM_PORT}
    for entry in load_config(config_path):
        if not entry.get("enabled", False) and not all_installed:
            continue
        directory = (config_path.parent / entry["directory"]).resolve()
        if not directory.is_dir():
            print(f"[skip] {entry['id']}: source directory not found: {directory}", flush=True)
            continue
        port = entry.get("port")
        if port is not None:
            if port in assigned_ports:
                raise ValueError(f"Port conflict: {port} already assigned ({entry['id']})")
            assigned_ports.add(port)
        cmd = [sys.executable if x == "{python}" else x for x in entry["command"]]
        # Absolute or relative local Python executable paths are allowed in trusted
        # configuration. Never use shell=True or commands supplied over HTTP.
        plan.append({"id": entry["id"], "cwd": directory, "command": cmd,
                     "port": port, "env": entry.get("env") or {}})
    return plan


def stop_children(children: list[tuple[str, subprocess.Popen]]) -> None:
    for name, process in reversed(children):
        if process.poll() is None:
            print(f"[stop] {name}", flush=True)
            process.terminate()
    for name, process in reversed(children):
        try:
            process.wait(timeout=7)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the local Axiom Workspace suite")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Trusted local module launch configuration")
    parser.add_argument("--all", action="store_true",
                        help="Include configured modules even if disabled by default")
    parser.add_argument("--dry-run", action="store_true", help="Inspect launch plan only")
    args = parser.parse_args(argv)
    config = args.config.resolve()
    try:
        plan = plan_modules(config, all_installed=args.all)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[error] Invalid workspace configuration: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Axiom: {sys.executable} desktop.py (port {AXIOM_PORT})")
        for item in plan:
            print(f"{item['id']}: cwd={item['cwd']}, port={item['port']}, "
                  f"command={item['command']}")
        return 0
    if busy(AXIOM_PORT):
        print("[error] Axiom port 5060 is already occupied. No suite processes started.",
              file=sys.stderr)
        return 2
    children = []
    try:
        for item in plan:
            if item["port"] and busy(item["port"]):
                print(f"[skip] {item['id']}: port {item['port']} already occupied. "
                      "Check the existing instance from Workspace.", flush=True)
                continue
            env = os.environ.copy()
            env.update(item["env"])
            print(f"[start] {item['id']}", flush=True)
            children.append((item["id"], subprocess.Popen(
                item["command"], cwd=item["cwd"], env=env)))
        env = os.environ.copy()
        env["AXIOM_HOST"] = "127.0.0.1"
        print("[start] Axiom: http://127.0.0.1:5060/workspace", flush=True)
        axiom = subprocess.Popen([sys.executable, "desktop.py"], cwd=ROOT, env=env)
        children.append(("axiom", axiom))
        reported = set()
        while axiom.poll() is None:
            for name, process in children[:-1]:
                if process.poll() is not None and name not in reported:
                    print(f"[exit] {name}: code {process.returncode}", flush=True)
                    reported.add(name)
            time.sleep(0.5)
        return int(axiom.returncode or 0)
    except KeyboardInterrupt:
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
