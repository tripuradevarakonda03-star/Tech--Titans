"""
Newline-delimited JSON message framing shared by the server and every
client (human or bot). One JSON object per line. This is intentionally
the only thing the network layer needs to agree on -- everything else
(what a message means, when it's valid) lives in game.py.

--- Client -> server message types ---
JOIN        {"type": "join", "name": str}
START       {"type": "start"}                       -- host only
ADD_BOTS    {"type": "add_bots", "count": int}       -- host only
RESPOND     {"type": "respond", "target": str}       -- answers whatever
                                                          PROMPT last asked
CHAT        {"type": "chat", "text": str}
ACCUSE      {"type": "accuse", "target": str}
LAST_WORDS  {"type": "last_words", "text": str}

--- Server -> client message types ---
LOBBY       {"type": "lobby", "players": [str], "host": str,
             "min_players": int, "started": bool}
ROLE        {"type": "role", "role": str, "team": str, "description": str}
                                                      -- private, one per client
PHASE       {"type": "phase", "phase": str, "round": int}
PROMPT      {"type": "prompt", "prompt_id": str, "message": str,
             "candidates": [str]}                     -- private, one per client
CHAT        {"type": "chat", "from": str, "text": str}
SUSPICION   {"type": "suspicion", "tally": {name: count}}
SYSTEM      {"type": "system", "text": str}           -- public announcement
PRIVATE     {"type": "private", "text": str}          -- private aside
GAME_OVER   {"type": "game_over", "winner": str, "roles": {name: {...}}}
ERROR       {"type": "error", "text": str}            -- rejected input, re-prompt
"""

from __future__ import annotations

import json
import socket


# Client -> server
JOIN = "join"
START = "start"
ADD_BOTS = "add_bots"
RESPOND = "respond"
CHAT = "chat"
ACCUSE = "accuse"
LAST_WORDS = "last_words"

# Server -> client
LOBBY = "lobby"
ROLE = "role"
PHASE = "phase"
PROMPT = "prompt"
SUSPICION = "suspicion"
SYSTEM = "system"
PRIVATE = "private"
GAME_OVER = "game_over"
ERROR = "error"

MALFORMED = "_malformed"  # internal marker; never sent on the wire


class ConnectionClosed(Exception):
    """Raised when the peer has closed the connection (clean EOF)."""


def send(sock: socket.socket, message: dict) -> None:
    """Serialize `message` as one line of JSON and send it whole."""
    data = (json.dumps(message) + "\n").encode("utf-8")
    sock.sendall(data)


class MessageReader:
    """
    Wraps a socket and yields one parsed JSON message per line.

    A single recv() is not guaranteed to end on a message boundary (TCP is
    a byte stream, not a message stream), so this buffers partial reads
    until a full line is available. A malformed line (bad JSON, not an
    object, missing "type") is reported back as {"type": MALFORMED}
    instead of raising -- a broken or hostile client should never be able
    to crash the reader thread and take the game down for everyone else.
    """

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._buf = b""

    def read(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionClosed()
            self._buf += chunk
            if len(self._buf) > 1_000_000:  # guard against an unbounded line flooding memory
                self._buf = b""
                return {"type": MALFORMED}
        line, _, self._buf = self._buf.partition(b"\n")
        try:
            msg = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {"type": MALFORMED}
        if not isinstance(msg, dict) or "type" not in msg or not isinstance(msg["type"], str):
            return {"type": MALFORMED}
        return msg
