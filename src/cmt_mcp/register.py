"""Register this server with Hermes Agent by editing ~/.hermes/config.yaml.

    uv run cmt-mcp-register hermes              # prompts for CMT email and password
    uv run cmt-mcp-register hermes --dry-run    # preview (password masked)

CMT_EMAIL / CMT_PASSWORD from the environment are used instead of prompting when set.
"""
import argparse
import getpass
import os
import shutil
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path.home() / ".hermes" / "config.yaml"


def build_entry(email: str, password: str) -> dict:
    return {
        "command": "uv",
        "args": ["--directory", str(REPO), "run", "cmt-mcp"],
        "env": {"CMT_EMAIL": email, "CMT_PASSWORD": password},
    }


def register_hermes(config_path: Path, email: str, password: str, name: str = "cmt", dry_run: bool = False) -> str:
    cfg = yaml.safe_load(config_path.read_text()) if config_path.exists() else None
    cfg = cfg or {}
    cfg.setdefault("mcp_servers", {})[name] = build_entry(email, password)
    text = yaml.safe_dump(cfg, sort_keys=False)
    if dry_run:
        return text
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        shutil.copy2(config_path, config_path.with_suffix(".yaml.bak"))  # note: yaml round-trip drops comments
    config_path.write_text(text)
    config_path.chmod(0o600)  # contains the CMT password
    return str(config_path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cmt-mcp-register", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("target", choices=["hermes"])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Hermes config path")
    ap.add_argument("--name", default="cmt", help="server name in mcp_servers")
    ap.add_argument("--dry-run", action="store_true", help="print the resulting YAML (password masked) and exit")
    a = ap.parse_args(argv)
    email = os.environ.get("CMT_EMAIL") or input("CMT email: ").strip()
    password = os.environ.get("CMT_PASSWORD") or getpass.getpass("CMT password (hidden): ")
    if not (email and password):
        sys.exit("Email and password are required.")
    out = register_hermes(a.config, email, password, a.name, a.dry_run)
    if a.dry_run:
        print(out.replace(password, "***"))
    else:
        print(f"Registered '{a.name}' in {out}\nReload in Hermes with /reload-mcp (or start a new `hermes chat`); verify with `hermes mcp test {a.name}`.")


if __name__ == "__main__":
    main()
