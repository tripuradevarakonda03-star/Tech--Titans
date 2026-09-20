#!/usr/bin/env python3
"""
Terminal Mafia -- server

CLI entry point for the player hosting the game. Parses arguments,
optionally pre-spawns bots, and runs the authoritative GameServer.
Everyone else connects with client.py (or gets auto-filled with
bot_client.py bots).

    python server.py [--port 5050] [--host 0.0.0.0] [--bots 0]
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

from mafia import colors as c
from mafia.game import GameServer
from mafia.roles import REQUIRED_PLAYERS

HERE = Path(__file__).resolve().parent


def local_lan_ip() -> str:
    """Best-effort guess at this machine's LAN-facing IP, for display only."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    c.enable_on_windows()
    parser = argparse.ArgumentParser(description="Host a Terminal Mafia game.")
    parser.add_argument("--port", type=int, default=5050, help="TCP port to listen on (default 5050)")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind (default 0.0.0.0, all interfaces)")
    parser.add_argument("--bots", type=int, default=0,
                         help=f"Number of AI bot players to add immediately (0-{REQUIRED_PLAYERS})")
    args = parser.parse_args()

    print(c.header("TERMINAL MAFIA -- SERVER", c.MAGENTA))
    print(f"Table size is fixed at {REQUIRED_PLAYERS} players "
          f"(2 Villager, 1 Soldier, 1 Detective, 1 Shapeshifter).")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Players on this LAN/hotspot connect with:")
    print(f"  {c.paint(f'python client.py {local_lan_ip()} {args.port}', c.CYAN)}")
    print(f"On this same machine, connect with:")
    print(f"  {c.paint(f'python client.py 127.0.0.1 {args.port}', c.CYAN)}")
    print("Once at least yourself has joined, type `start` in your own client "
          "to begin -- empty seats are auto-filled with bots.")
    print(c.divider())

    bot_client_path = str(HERE / "bot_client.py")
    server = GameServer(host=args.host, port=args.port, num_bots=max(0, args.bots),
                         bot_client_path=bot_client_path, match_history_dir=HERE / "match_history")
    try:
        server.start()
    except KeyboardInterrupt:
        print(f"\n{c.YELLOW}Shutting down...{c.RESET}")
    except OSError as e:
        print(f"{c.RED}Could not start the server: {e}{c.RESET}")
        sys.exit(1)
    finally:
        server.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{c.YELLOW}Interrupted.{c.RESET}")
        sys.exit(0)
