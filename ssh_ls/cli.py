import argparse
import shlex
import sys
from pathlib import Path
from . import __version__
from .launch import launch
from .service import Service


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find SSH hosts from config and history. Pick one, connect, return to your shell.")
    parser.add_argument("--version", action="version", version=f"ssh-ls {__version__}")
    parser.add_argument("--config", type=Path, help="Use an alternate SSH config (also passed to ssh -F)")
    parser.add_argument("--history", type=Path, action="append", help="History file to scan; repeat for more files")
    parser.add_argument("--no-history", action="store_true", help="Do not read shell histories")
    parser.add_argument("--demo", action="store_true", help="Use fictional hosts, in-memory state and no SSH execution")
    parser.add_argument("--doctor", action="store_true", help="Print local diagnostics without contacting servers")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII borders and indicators")
    args = parser.parse_args(argv)
    service = Service(configs=[args.config] if args.config else None, histories=args.history, no_history=args.no_history, demo=args.demo)
    if args.ascii:
        service.settings["ascii"] = True
    if args.doctor:
        print(service.diagnose())
        return 1 if service.state_error else 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("TUI requires an interactive terminal. Use --doctor for a non-interactive check.")
    from .ui import SSHApp
    request = SSHApp(service).run()
    if request is None:
        return 0
    if args.demo:
        print("DEMO (not executed): " + shlex.join(service.argv(request.host, request.command)))
        return 0
    try:
        service.argv(request.host, request.command)
        service.record_use(request.host)
    except (OSError, ValueError) as exc:
        print(f"Not connected: could not validate or save connection state: {exc}", file=sys.stderr)
        return 1
    result = launch(request.host, request.command)
    if result:
        print(f"SSH exited with status {result}. Original errors are above. Run ssh-ls --doctor for local checks; use v in the TUI for an explicit config preview.", file=sys.stderr)
    return 128 - result if result < 0 else result
