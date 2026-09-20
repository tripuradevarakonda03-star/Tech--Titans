#!/usr/bin/env python3
"""
Terminal Mafia -- client

Terminal UI for a human player. Connects to a running server.py, renders
whatever it broadcasts, and relays typed input back over the same
newline-delimited JSON protocol every bot_client.py also speaks.

    python client.py <host-ip> <port>
    python client.py                    (tries to auto-discover a server on the LAN)
"""

from __future__ import annotations

import random
import socket
import sys
import threading

from mafia import colors as c
from mafia import discovery
from mafia import protocol as proto


class Client:
    def __init__(self, host: str, port: int, name: str):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self._reader = proto.MessageReader(self.sock)
        self._pending_prompt: dict | None = None
        self._lock = threading.Lock()

    def send(self, message: dict) -> None:
        try:
            proto.send(self.sock, message)
        except OSError:
            print(f"{c.RED}Lost connection to the server.{c.RESET}")

    def listen_forever(self) -> None:
        try:
            while True:
                msg = self._reader.read()
                self._handle(msg)
        except (proto.ConnectionClosed, OSError):
            print(f"\n{c.RED}Disconnected from the server.{c.RESET}")

    def _handle(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == proto.LOBBY:
            players = msg.get("players", [])
            host = msg.get("host")
            tag = " (you are host)" if host == self.name else f" (host: {host})"
            print(f"{c.CYAN}Lobby: {', '.join(players)}  [{len(players)}/{msg.get('min_players')}]{tag}{c.RESET}")
            if host == self.name and not msg.get("started"):
                print(f"{c.DIM}Type 'start' when ready (empty seats auto-fill with bots), "
                      f"or 'bots <n>' to add some now.{c.RESET}")
        elif mtype == proto.ROLE:
            print(c.header(f"YOUR ROLE: {msg['role'].upper()}", c.MAGENTA))
            print(f"Team: {msg['team']}")
            print(msg["description"])
            print(c.divider())
        elif mtype == proto.PHASE:
            phase = msg.get("phase")
            label = {
                "night": f"NIGHT {msg.get('round')} FALLS",
                "day_reveal": f"DAY {msg.get('round')} BREAKS",
                "day_discuss": "DISCUSSION",
                "day_vote": "VOTING",
            }.get(phase, phase.upper())
            color = {"night": c.BLUE, "day_reveal": c.YELLOW}.get(phase, c.CYAN)
            print(c.header(label, color))
        elif mtype == proto.PROMPT:
            self._pending_prompt = msg
            print(f"{c.GREEN}{msg['message']}{c.RESET}")
            for i, name in enumerate(msg.get("candidates", []), start=1):
                print(f"   {i}. {name}")
            if msg.get("prompt_id") == "last_words":
                print(f"{c.DIM}(just type your message, or press Enter to skip){c.RESET}")
            else:
                print(f"{c.DIM}(type the number or the name){c.RESET}")
        elif mtype == proto.CHAT:
            print(f'   {c.WHITE}{msg.get("from")}: "{msg.get("text")}"{c.RESET}')
        elif mtype == proto.SUSPICION:
            tally = msg.get("tally", {})
            if tally:
                line = ", ".join(f"{n} ({v})" for n, v in sorted(tally.items(), key=lambda kv: -kv[1]))
                print(f"{c.DIM}Suspicion so far -- {line}{c.RESET}")
        elif mtype == proto.SYSTEM:
            print(f"{c.YELLOW}{msg.get('text')}{c.RESET}")
        elif mtype == proto.PRIVATE:
            print(f"{c.CYAN}{msg.get('text')}{c.RESET}")
        elif mtype == proto.GAME_OVER:
            print(c.header("GAME OVER", c.MAGENTA))
            winner = msg.get("winner")
            if winner == "Survivors":
                print(f"{c.GREEN}{c.BOLD}TEAM 2 -- SURVIVORS WIN!{c.RESET}")
            elif winner == "Hunters":
                print(f"{c.RED}{c.BOLD}TEAM 1 -- HUNTERS WIN!{c.RESET}")
            else:
                print(f"{c.YELLOW}NO RESOLUTION -- IT'S A STANDOFF{c.RESET}")
            print(c.divider("="))
            print(f"{c.BOLD}FINAL ROLE REVEAL{c.RESET}")
            print(c.divider("="))
            for name, info in msg.get("roles", {}).items():
                status = f"{c.GREEN}ALIVE{c.RESET}" if info.get("alive") else f"{c.DIM}ELIMINATED{c.RESET}"
                print(f"   {name:<18} {info.get('role') or '?':<13} ({info.get('team') or '?':<9}) - {status}")
            print(c.divider("="))
        elif mtype == proto.ERROR:
            print(f"{c.RED}{msg.get('text')}{c.RESET}")


def resolve_target(raw: str, candidates: list[str]) -> str | None:
    raw = raw.strip()
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(candidates):
            return candidates[idx - 1]
        return None
    for name in candidates:
        if name.lower() == raw.lower():
            return name
    return None


def main() -> None:
    c.enable_on_windows()
    print(c.header("TERMINAL MAFIA", c.MAGENTA))

    if len(sys.argv) >= 3:
        host, port = sys.argv[1], int(sys.argv[2])
    else:
        print(f"{c.DIM}Looking for a server on the local network...{c.RESET}")
        found = discovery.find_server(timeout=2.5)
        if found:
            host, port = found
            print(f"{c.GREEN}Found one at {host}:{port}{c.RESET}")
        else:
            print(f"{c.YELLOW}Nothing answered. Enter connection details manually.{c.RESET}")
            host = input("Host/IP (e.g. 127.0.0.1): ").strip() or "127.0.0.1"
            port = int(input("Port (e.g. 5050): ").strip() or "5050")

    name = input("Your name: ").strip() or f"Player{random.randint(100, 999)}"

    client = Client(host, port, name)
    client.send({"type": proto.JOIN, "name": name})
    threading.Thread(target=client.listen_forever, daemon=True).start()

    try:
        while True:
            try:
                raw = input()
            except EOFError:
                break
            raw = raw.strip()
            if not raw:
                if client._pending_prompt and client._pending_prompt.get("prompt_id") == "last_words":
                    client.send({"type": proto.LAST_WORDS, "text": ""})
                    client._pending_prompt = None
                continue
            if raw.lower() == "start":
                client.send({"type": proto.START})
            elif raw.lower().startswith("bots "):
                try:
                    count = int(raw.split(None, 1)[1])
                except (IndexError, ValueError):
                    print(f"{c.RED}Usage: bots <number>{c.RESET}")
                else:
                    client.send({"type": proto.ADD_BOTS, "count": count})
            elif raw.lower().startswith("accuse "):
                client.send({"type": proto.ACCUSE, "target": raw.split(None, 1)[1].strip()})
            elif client._pending_prompt is not None:
                prompt = client._pending_prompt
                if prompt.get("prompt_id") == "last_words":
                    client.send({"type": proto.LAST_WORDS, "text": raw})
                    client._pending_prompt = None
                else:
                    target = resolve_target(raw, prompt.get("candidates", []))
                    if target is None:
                        print(f"{c.RED}Not a valid choice -- pick a listed number or name.{c.RESET}")
                    else:
                        client.send({"type": proto.RESPOND, "target": target})
                        client._pending_prompt = None
            else:
                client.send({"type": proto.CHAT, "text": raw})
    except KeyboardInterrupt:
        pass
    finally:
        try:
            client.sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
