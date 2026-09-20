#!/usr/bin/env python3
"""
Terminal Mafia -- bot client

Speaks the exact same wire protocol as client.py, so from the server's
point of view a bot is indistinguishable from a slow-typing human -- it
just answers its own prompts automatically instead of waiting on a
keyboard. Used to auto-fill empty seats (`server.py --bots N`, or `bots
<n>` typed into a real client) and for solo testing/demos.

    python bot_client.py <host> <port> [name]
"""

from __future__ import annotations

import random
import socket
import sys
import time

from mafia import protocol as proto
from mafia.roles import Role

BOT_NAME_POOL = ["Root", "Sudo", "Daemon", "Kernel", "Byte", "Cache", "Ghost", "Nyx", "Cipher", "Proxy"]

DISCUSSION_LINES = [
    "I don't trust the way {other} has been acting.",
    "We need to think carefully before we vote.",
    "Has anyone else noticed {other} being unusually quiet?",
    "I still don't have a strong read on anyone.",
    "{other}, care to explain yourself?",
    "Let's not be hasty -- think this through with me.",
    "Something about last night still isn't sitting right with me.",
]
DETECTIVE_LINES = [
    "I've been watching {other} closely, and something's off.",
    "Call it a hunch, but I don't trust {other} one bit.",
    "I'm not backing down from suspecting {other}.",
    "Everyone's being too quiet about {other}, and that bothers me.",
    "Mark my words -- {other} is the one we should be watching.",
]


class Bot:
    def __init__(self, host: str, port: int, name: str):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self._reader = proto.MessageReader(self.sock)
        self.role: str | None = None
        self.hunch: str | None = None
        self.last_roster: list[str] = []

    def send(self, message: dict) -> None:
        try:
            proto.send(self.sock, message)
        except OSError:
            pass

    def run(self) -> None:
        self.send({"type": proto.JOIN, "name": self.name, "is_bot": True})
        try:
            while True:
                msg = self._reader.read()
                if not self._handle(msg):
                    return  # rejected for a reason retrying can't fix (table full / already started)
        except (proto.ConnectionClosed, OSError):
            return

    def _handle(self, msg: dict) -> bool:
        """Processes one message. Returns False to signal the bot should give up and exit."""
        mtype = msg.get("type")
        if mtype == proto.ERROR and self.role is None:
            if "already taken" in str(msg.get("text", "")):
                # Almost certainly a name collision with another bot that
                # grabbed the same random name from the same small pool --
                # pick a fresh, near-certainly-unique name and retry, rather
                # than sitting connected-but-rejected forever (silently
                # leaving a seat empty).
                self.name = f"{random.choice(BOT_NAME_POOL)}-{random.randint(1000, 9999)} (Bot)"
                self.send({"type": proto.JOIN, "name": self.name, "is_bot": True})
            else:
                return False  # table full / already started / etc -- retrying won't help
            return True
        if mtype == proto.ROLE:
            self.role = msg.get("role")
        elif mtype == proto.LOBBY:
            self.last_roster = msg.get("players", [])
        elif mtype == proto.PHASE and msg.get("phase") == "day_discuss":
            self._maybe_chat()
        elif mtype == proto.PROMPT:
            self._answer_prompt(msg)
        elif mtype == proto.GAME_OVER:
            return False  # game's done -- exit normally
        return True

    def _maybe_chat(self) -> None:
        others = [n for n in self.last_roster if n != self.name]
        if not others:
            return
        time.sleep(random.uniform(0.3, 1.2))
        pool = DETECTIVE_LINES if self.role == Role.DETECTIVE.value else DISCUSSION_LINES
        line = random.choice(pool)
        if "{other}" in line:
            line = line.format(other=random.choice(others))
        self.send({"type": proto.CHAT, "text": line})

    def _answer_prompt(self, msg: dict) -> None:
        candidates = msg.get("candidates", [])
        prompt_id = msg.get("prompt_id")
        time.sleep(random.uniform(0.4, 1.1))  # a beat of "thinking", same pacing as the single-terminal build

        if prompt_id == "last_words":
            self.send({"type": proto.LAST_WORDS, "text": ""})
            return
        if not candidates:
            return

        if prompt_id == "vote" and self.role == Role.DETECTIVE.value:
            if self.hunch is None or self.hunch not in candidates:
                self.hunch = random.choice(candidates)
            target = self.hunch if random.random() < 0.85 else random.choice(candidates)
        else:
            target = random.choice(candidates)
        self.send({"type": proto.RESPOND, "target": target})


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python bot_client.py <host> <port> [name]")
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else f"{random.choice(BOT_NAME_POOL)}-{random.randint(100, 999)} (Bot)"
    Bot(host, port, name).run()


if __name__ == "__main__":
    main()
