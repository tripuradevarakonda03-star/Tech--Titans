"""
UDP broadcast/reply so a client can find a Terminal Mafia server on the
local network or mobile hotspot without anyone having to type an IP
address. Best-effort only: some hotspots and locked-down networks block
broadcast traffic, so callers must always be ready to fall back to
asking the player for a host/port manually if this doesn't turn anything
up within a couple of seconds.
"""

from __future__ import annotations

import json
import socket

DISCOVERY_PORT = 50555
MAGIC = "TERMINAL_MAFIA_V1"


def make_server_socket() -> socket.socket:
    """Server side: a non-blocking UDP socket bound to the discovery port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", DISCOVERY_PORT))
    sock.setblocking(False)
    return sock


def answer_pending_probe(disco_sock: socket.socket, game_port: int) -> None:
    """
    Server side: reply to at most one waiting discovery probe, if any.
    Meant to be polled periodically from the server's main loop -- never
    blocks, since disco_sock is non-blocking.
    """
    try:
        data, addr = disco_sock.recvfrom(1024)
    except BlockingIOError:
        return
    except OSError:
        return
    try:
        msg = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(msg, dict) or msg.get("magic") != MAGIC or msg.get("type") != "ping":
        return
    reply = json.dumps({"magic": MAGIC, "type": "pong", "port": game_port}).encode("utf-8")
    try:
        disco_sock.sendto(reply, addr)
    except OSError:
        pass


def find_server(timeout: float = 2.0) -> tuple[str, int] | None:
    """
    Client side: broadcast a probe and wait up to `timeout` seconds for a
    reply. Returns (host, port) on success, None if nothing answered.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    probe = json.dumps({"magic": MAGIC, "type": "ping"}).encode("utf-8")
    try:
        sock.sendto(probe, ("<broadcast>", DISCOVERY_PORT))
        data, addr = sock.recvfrom(1024)
        msg = json.loads(data.decode("utf-8"))
        if isinstance(msg, dict) and msg.get("magic") == MAGIC and msg.get("type") == "pong":
            return addr[0], int(msg["port"])
    except (socket.timeout, OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass
    finally:
        sock.close()
    return None
