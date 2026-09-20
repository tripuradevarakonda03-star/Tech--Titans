"""
GameServer: connection handling + the night/day phase state machine.

Networking model: the server is authoritative. It accepts TCP
connections and spawns one lightweight reader thread per client; those
threads only ever push incoming messages onto a single thread-safe
queue. All game-state mutation (role assignment, phase transitions,
vote tallying, win checks) happens on one thread -- the main loop that
drains that queue -- so there is no locking to get wrong around the
actual game logic. Sending to a given client is independently
thread-safe (each PlayerConn has its own write lock), since broadcasts
happen from the main thread but a disconnect can be detected and
reported from a reader thread at any time.
"""

from __future__ import annotations

import queue
import random
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import discovery
from . import protocol as proto
from .roles import (
    MAX_DEATHS,
    REQUIRED_PLAYERS,
    ROLE_DESCRIPTIONS,
    Role,
    Team,
    role_distribution,
    team_of,
)

NIGHT_TIME = 45          # seconds allotted for night actions before defaulting
DAY_DISCUSS_TIME = 45    # seconds of open discussion
DAY_VOTE_TIME = 30       # seconds to cast a vote before defaulting
ROUND_RESULT_HOLD = 10   # seconds each round's result stays up before the next begins
MAX_ROUNDS = 15          # safety net so a pathological run of ties/saves can't loop forever


@dataclass
class PlayerConn:
    """One seat at the table -- a human client or a bot_client.py process, indistinguishable to the server."""
    name: str
    sock: socket.socket
    is_bot: bool = False
    role: Role | None = None
    alive: bool = True
    connected: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def send(self, message: dict) -> None:
        if not self.connected:
            return
        with self._lock:
            try:
                proto.send(self.sock, message)
            except OSError:
                self.connected = False


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 5050, num_bots: int = 0,
                 bot_client_path: str | None = None, match_history_dir: str | Path = "match_history"):
        self.host = host
        self.port = port
        self.initial_bots = num_bots
        self.bot_client_path = bot_client_path  # path to bot_client.py, for subprocess spawning
        self.match_history_dir = Path(match_history_dir)

        self.players: dict[str, PlayerConn] = {}  # name -> conn, insertion order = join order
        self.host_name: str | None = None
        self.started = False
        self.round_no = 0
        self.total_deaths = 0
        self.winner: Team | None = None
        self.log: list[str] = []
        self.night_result: tuple[str, str] | None = None  # ("killed"|"saved", name)
        self.detective_hunch: str | None = None
        self.suspicion: dict[str, int] = {}
        self._bot_procs: list[subprocess.Popen] = []

        self.events: queue.Queue = queue.Queue()
        self._listener: socket.socket | None = None
        self._disco_sock = None
        self._sock_to_name: dict[socket.socket, str] = {}

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((self.host, self.port))
        self._listener.listen()
        threading.Thread(target=self._accept_loop, daemon=True).start()

        try:
            self._disco_sock = discovery.make_server_socket()
            threading.Thread(target=self._discovery_loop, daemon=True).start()
        except OSError:
            self._disco_sock = None  # discovery is best-effort; a game still works without it

        if self.initial_bots:
            self.spawn_bots(self.initial_bots)

        self._main_loop()

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
        if self._disco_sock:
            try:
                self._disco_sock.close()
            except OSError:
                pass
        for proc in self._bot_procs:
            if proc.poll() is None:
                proc.terminate()
        # Actually wait for them to die (briefly) rather than fire-and-forget --
        # otherwise a slow test run can pile up straggler bot subprocesses that
        # starve the *next* test's bot subprocesses of CPU/scheduling time.
        for proc in self._bot_procs:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass

    def _discovery_loop(self) -> None:
        while self._disco_sock is not None:
            try:
                discovery.answer_pending_probe(self._disco_sock, self.port)
            except OSError:
                return
            time.sleep(0.2)

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _addr = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._reader_thread, args=(conn,), daemon=True).start()

    def _reader_thread(self, sock: socket.socket) -> None:
        reader = proto.MessageReader(sock)
        try:
            while True:
                msg = reader.read()
                self.events.put(("message", sock, msg))
        except (proto.ConnectionClosed, OSError):
            self.events.put(("disconnect", sock, None))

    def spawn_bots(self, count: int) -> None:
        """Launch `count` bot_client.py subprocesses that connect back over loopback."""
        if not self.bot_client_path:
            return
        for _ in range(count):
            proc = subprocess.Popen(
                [sys.executable, self.bot_client_path, "127.0.0.1", str(self.port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._bot_procs.append(proc)

    # ------------------------------------------------------------------
    # Broadcast / logging helpers
    # ------------------------------------------------------------------
    def broadcast(self, message: dict, *, exclude: set[str] = frozenset()) -> None:
        for name, conn in self.players.items():
            if conn.connected and name not in exclude:
                conn.send(message)

    def announce(self, text: str) -> None:
        self.broadcast({"type": proto.SYSTEM, "text": text})

    def log_event(self, text: str) -> None:
        self.log.append(f"Round {self.round_no}: {text}")

    def alive_names(self) -> list[str]:
        return [n for n, c in self.players.items() if c.alive]

    def connected_alive_names(self) -> list[str]:
        return [n for n, c in self.players.items() if c.alive and c.connected]

    # ------------------------------------------------------------------
    # Main loop: lobby, then the game itself
    # ------------------------------------------------------------------
    def _main_loop(self) -> None:
        self._run_lobby()
        if not self.started:
            return  # server was stopped before anyone started a game
        self._run_game()

    def _run_lobby(self) -> None:
        while not self.started:
            try:
                kind, sock, payload = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            if kind == "disconnect":
                self._handle_disconnect(sock)
                continue
            msg = payload
            mtype = msg.get("type")
            if mtype == proto.JOIN:
                self._handle_join(sock, msg)
            elif mtype == proto.START:
                self._handle_start(sock)
            elif mtype == proto.ADD_BOTS:
                self._handle_add_bots(sock, msg)
            # chat before the game starts is harmless lobby banter
            elif mtype == proto.CHAT:
                name = self._sock_to_name.get(sock)
                if name:
                    self.broadcast({"type": proto.CHAT, "from": name, "text": str(msg.get("text", ""))[:500]})

    def _handle_join(self, sock: socket.socket, msg: dict) -> None:
        name = str(msg.get("name") or "").strip()[:32]
        if not name:
            proto.send(sock, {"type": proto.ERROR, "text": "A name is required to join."})
            return

        existing = self.players.get(name)
        if existing is not None:
            if self.started and not existing.connected:
                # Reconnect: same seat, same role, just a fresh socket.
                existing.sock = sock
                existing.connected = True
                self._sock_to_name[sock] = name
                existing.send({"type": proto.LOBBY, "players": list(self.players), "host": self.host_name,
                               "min_players": REQUIRED_PLAYERS, "started": self.started})
                if existing.role is not None:
                    existing.send({"type": proto.ROLE, "role": existing.role.value,
                                   "team": team_of(existing.role).value,
                                   "description": ROLE_DESCRIPTIONS[existing.role]})
                self.announce(f"{name} reconnected.")
                return
            proto.send(sock, {"type": proto.ERROR, "text": f"The name '{name}' is already taken at this table."})
            return

        if self.started:
            proto.send(sock, {"type": proto.ERROR, "text": "This game has already started."})
            return
        if len(self.players) >= REQUIRED_PLAYERS:
            proto.send(sock, {"type": proto.ERROR, "text": "This table is already full (5/5)."})
            return

        is_bot = bool(msg.get("is_bot", False))
        self.players[name] = PlayerConn(name=name, sock=sock, is_bot=is_bot)
        self._sock_to_name[sock] = name
        if self.host_name is None and not is_bot:
            # The host must be a real person -- bots never send START, so if
            # a bot ended up "hosting" (e.g. pre-spawned via --bots before any
            # human joined), the lobby would sit there forever with no one
            # able to start it.
            self.host_name = name
        self._broadcast_lobby()
        self.announce(f"{name} joined ({len(self.players)}/{REQUIRED_PLAYERS}).")
        self._auto_start_if_all_bots()

    def _auto_start_if_all_bots(self) -> None:
        # A fully-autonomous table (e.g. spun up for a demo/test with no
        # human players at all) has no one who could ever type "start", so
        # the server starts it itself the moment the table fills.
        if (not self.started and len(self.players) == REQUIRED_PLAYERS
                and all(p.is_bot for p in self.players.values())):
            self.started = True
            self._deal_roles()
            self._broadcast_lobby()

    def _broadcast_lobby(self) -> None:
        self.broadcast({"type": proto.LOBBY, "players": list(self.players), "host": self.host_name,
                         "min_players": REQUIRED_PLAYERS, "started": self.started})

    def _handle_add_bots(self, sock: socket.socket, msg: dict) -> None:
        name = self._sock_to_name.get(sock)
        if name != self.host_name:
            proto.send(sock, {"type": proto.ERROR, "text": "Only the host can add bots."})
            return
        try:
            count = int(msg.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        room = REQUIRED_PLAYERS - len(self.players)
        count = max(0, min(count, room))
        if count:
            self.spawn_bots(count)

    def _handle_start(self, sock: socket.socket) -> None:
        name = self._sock_to_name.get(sock)
        if name != self.host_name:
            proto.send(sock, {"type": proto.ERROR, "text": "Only the host can start the game."})
            return
        room = REQUIRED_PLAYERS - len(self.players)
        if room > 0:
            self.spawn_bots(room)  # auto-fill any empty seats, same convenience as the single-terminal build
        # Give freshly-spawned bot subprocesses a moment to connect and join.
        deadline = time.time() + 5.0
        while len(self.players) < REQUIRED_PLAYERS and time.time() < deadline:
            try:
                kind, s, payload = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            if kind == "disconnect":
                self._handle_disconnect(s)
            elif payload.get("type") == proto.JOIN:
                self._handle_join(s, payload)
        if len(self.players) != REQUIRED_PLAYERS:
            proto.send(sock, {"type": proto.ERROR,
                               "text": f"Need exactly {REQUIRED_PLAYERS} players to start (have {len(self.players)})."})
            return
        self.started = True
        self._deal_roles()
        self._broadcast_lobby()

    def _deal_roles(self) -> None:
        roles = role_distribution(len(self.players))
        random.shuffle(roles)
        for conn, role in zip(self.players.values(), roles):
            conn.role = role
            conn.send({"type": proto.ROLE, "role": role.value, "team": team_of(role).value,
                       "description": ROLE_DESCRIPTIONS[role]})
        self.log_event("Roles dealt: " + ", ".join(f"{n}={c.role.value}" for n, c in self.players.items()))

    # ------------------------------------------------------------------
    # The game itself
    # ------------------------------------------------------------------
    def _run_game(self) -> None:
        self.announce("Roles have been secretly dealt. The first night begins shortly.")
        while self.round_no < MAX_ROUNDS and self.winner is None:
            self.round_no += 1
            self._night_phase()
            if self.winner is None:
                self._day_phase()
            if self.winner is None:
                self._hold_for_next_round()
        if self.winner is None:
            self.log_event("The round limit was reached with no resolution.")
        self._finish_game()

    def _find_by_role(self, role: Role) -> str | None:
        for name, conn in self.players.items():
            if conn.alive and conn.role is role:
                return name
        return None

    def _collect_responses(self, expected: list[str], timeout_total: float) -> dict[str, str]:
        """
        Waits up to `timeout_total` seconds for a RESPOND from each name in
        `expected`. Any CHAT/ACCUSE arriving meanwhile is still processed
        and broadcast immediately -- players aren't frozen out of talking
        just because someone else's prompt is still open. Disconnects are
        handled inline. Returns whatever answers came in; callers must
        supply sensible defaults for names missing from the result.
        """
        answers: dict[str, str] = {}
        deadline = time.time() + timeout_total
        expected_set = set(expected)
        while len(answers) < len(expected_set) and time.time() < deadline:
            remaining = deadline - time.time()
            try:
                kind, sock, payload = self.events.get(timeout=max(0.05, remaining))
            except queue.Empty:
                break
            if kind == "disconnect":
                self._handle_disconnect(sock)
                continue
            msg = payload
            name = self._sock_to_name.get(sock)
            mtype = msg.get("type")
            if mtype == proto.RESPOND and name in expected_set and name not in answers:
                target = str(msg.get("target", ""))
                answers[name] = target
            elif mtype == proto.CHAT and name:
                self.broadcast({"type": proto.CHAT, "from": name, "text": str(msg.get("text", ""))[:500]})
            elif mtype == proto.ACCUSE and name:
                self._handle_accuse(name, msg)
            elif mtype == proto.LAST_WORDS and name:
                self.broadcast({"type": proto.SYSTEM, "text": f'{name} (last words): "{str(msg.get("text",""))[:300]}"'})
        return answers

    def _handle_accuse(self, accuser: str, msg: dict) -> None:
        target = str(msg.get("target", ""))
        if target not in self.players:
            return
        self.suspicion[target] = self.suspicion.get(target, 0) + 1
        self.broadcast({"type": proto.SYSTEM, "text": f"{accuser} publicly accuses {target}."})
        self.broadcast({"type": proto.SUSPICION, "tally": dict(self.suspicion)})

    # -- night --------------------------------------------------------
    def _night_phase(self) -> None:
        self.broadcast({"type": proto.PHASE, "phase": "night", "round": self.round_no})
        self.night_result = None
        alive = self.alive_names()

        soldier = self._find_by_role(Role.SOLDIER)
        shapeshifter = self._find_by_role(Role.SHAPESHIFTER)

        if soldier and self.players[soldier].connected:
            self.players[soldier].send({"type": proto.PROMPT, "prompt_id": "protect",
                                         "message": "Choose a player to protect tonight:", "candidates": alive})
        if shapeshifter and self.players[shapeshifter].connected:
            targets = [n for n in alive if n != shapeshifter]
            self.players[shapeshifter].send({"type": proto.PROMPT, "prompt_id": "kill",
                                              "message": "Choose a player to eliminate tonight:", "candidates": targets})

        expected = [n for n in (soldier, shapeshifter) if n]
        answers = self._collect_responses(expected, NIGHT_TIME)

        protect_target = answers.get(soldier) if soldier else None
        if protect_target not in self.players:
            protect_target = random.choice(alive) if soldier else None  # soldier defaulted (timeout/disconnect)

        kill_target = answers.get(shapeshifter) if shapeshifter else None
        valid_kill_targets = [n for n in alive if n != shapeshifter]
        if kill_target not in valid_kill_targets:
            kill_target = random.choice(valid_kill_targets) if valid_kill_targets else None

        if soldier:
            self.log_event(f"The Soldier chose to shield {protect_target}.")
        if kill_target:
            self._resolve_night_kill(kill_target, protect_target)

    def _resolve_night_kill(self, target: str, protected: str | None) -> None:
        if protected == target:
            self.night_result = ("saved", target)
            self.log_event(f"{target} was attacked but the Soldier's shield held.")
        else:
            self.players[target].alive = False
            self.total_deaths += 1
            self.night_result = ("killed", target)
            self.log_event(f"{target} was eliminated during the night.")

    # -- day ------------------------------------------------------------
    def _day_phase(self) -> None:
        self.broadcast({"type": proto.PHASE, "phase": "day_reveal", "round": self.round_no})
        self._reveal_night_result()

        if self.total_deaths >= MAX_DEATHS:
            self.winner = Team.HUNTERS
            self.log_event(f"{MAX_DEATHS} players are dead. The Shapeshifter wins by attrition.")
            return

        alive = self.alive_names()
        if len(alive) <= 1:
            self.winner = Team.HUNTERS
            return

        self.broadcast({"type": proto.PHASE, "phase": "day_discuss", "round": self.round_no,
                         "seconds": DAY_DISCUSS_TIME})
        self.announce(f"Discussion is open for {DAY_DISCUSS_TIME} seconds. Chat freely, or `accuse <name>`.")
        self._collect_responses([], DAY_DISCUSS_TIME)  # no one is "expected"; just drains chat/accuse for the window

        votes = self._collect_votes(alive)
        self._resolve_votes(votes)

    def _reveal_night_result(self) -> None:
        if self.night_result is None:
            return
        kind, name = self.night_result
        if kind == "saved":
            self.announce("The sun rises -- and everyone is still breathing. The Soldier's shield held!")
            return
        self.announce(f"The sun rises to grim news: {name} was found dead.")
        alive = self.connected_alive_names()
        reporter = random.choice(alive) if alive else None
        if reporter:
            self.announce(f"{reporter} reports the body to the group.")
            self.log_event(f"{reporter} reported {name}'s death.")

    def _collect_votes(self, alive: list[str]) -> dict[str, str]:
        self.broadcast({"type": proto.PHASE, "phase": "day_vote", "round": self.round_no, "seconds": DAY_VOTE_TIME})
        for name in alive:
            conn = self.players[name]
            if not conn.connected:
                continue
            candidates = [n for n in alive if n != name]
            conn.send({"type": proto.PROMPT, "prompt_id": "vote",
                       "message": "Who do you vote for?", "candidates": candidates})
        answers = self._collect_responses(alive, DAY_VOTE_TIME)
        votes: dict[str, str] = {}
        for voter in alive:
            candidates = [n for n in alive if n != voter]
            target = answers.get(voter)
            if target not in candidates:
                target = self._bot_vote_choice(voter, candidates) if self.players[voter].is_bot else (
                    random.choice(candidates) if candidates else None)
            if target:
                votes[voter] = target
        return votes

    def _bot_vote_choice(self, voter: str, candidates: list[str]) -> str:
        """Mirrors the single-terminal build: a Detective bot settles on one persistent
        hunch and mostly sticks with it -- suspicion, not evidence. Everyone else guesses."""
        conn = self.players.get(voter)
        if conn and conn.role is Role.DETECTIVE:
            if self.detective_hunch is None or self.detective_hunch not in candidates:
                self.detective_hunch = random.choice(candidates) if candidates else None
            if self.detective_hunch and random.random() < 0.85:
                return self.detective_hunch
        return random.choice(candidates) if candidates else None

    def _resolve_votes(self, votes: dict[str, str]) -> None:
        tally: dict[str, int] = {}
        for target in votes.values():
            tally[target] = tally.get(target, 0) + 1
        self.broadcast({"type": proto.SYSTEM, "text": "VOTE TALLY: " +
                         ", ".join(f"{n} ({c})" for n, c in sorted(tally.items(), key=lambda kv: -kv[1]))})
        if not tally:
            self.announce("No votes were cast. No one is eliminated today.")
            self.log_event("No votes cast; no elimination.")
            return

        max_votes = max(tally.values())
        top = [n for n, c in tally.items() if c == max_votes]
        if len(top) > 1:
            names = ", ".join(top)
            self.announce(f"It's a tie between {names}. No one is eliminated today.")
            self.log_event(f"Vote tied ({names}); no elimination.")
            return

        eliminated = top[0]
        conn = self.players[eliminated]
        if conn.connected:
            conn.send({"type": proto.PROMPT, "prompt_id": "last_words",
                       "message": "You've been voted out. Any last words? (blank to skip)", "candidates": []})
            self._collect_responses([], 8.0)
        conn.alive = False
        self.announce(f"{eliminated} has been voted out by the group.")

        if conn.role is Role.SHAPESHIFTER:
            self.announce(f"{eliminated} was the Shapeshifter!")
            self.log_event(f"{eliminated} (the Shapeshifter) was voted out.")
            self.winner = Team.SURVIVORS
            return

        self.total_deaths += 1
        self.announce(f"{eliminated} was not the Shapeshifter...")
        self.log_event(f"{eliminated} ({conn.role.value}) was voted out -- not the Shapeshifter.")
        if self.total_deaths >= MAX_DEATHS:
            self.winner = Team.HUNTERS
            self.log_event(f"{MAX_DEATHS} players are dead. The Shapeshifter wins by attrition.")

    def _hold_for_next_round(self) -> None:
        self.announce(f"Next round begins in {ROUND_RESULT_HOLD} seconds...")
        self._collect_responses([], ROUND_RESULT_HOLD)

    # ------------------------------------------------------------------
    # Ending
    # ------------------------------------------------------------------
    def _finish_game(self) -> None:
        roles = {name: {"role": conn.role.value if conn.role else None,
                         "team": team_of(conn.role).value if conn.role else None,
                         "alive": conn.alive}
                 for name, conn in self.players.items()}
        winner_value = self.winner.value if self.winner else None
        self.broadcast({"type": proto.GAME_OVER, "winner": winner_value, "roles": roles, "log": list(self.log)})
        self._write_match_history(winner_value, roles)

    def _write_match_history(self, winner_value: str | None, roles: dict) -> None:
        try:
            self.match_history_dir.mkdir(parents=True, exist_ok=True)
            fname = self.match_history_dir / f"{time.strftime('%Y-%m-%d_%H%M%S')}.log"
            lines = [
                "Terminal Mafia -- match record",
                f"Winner: {winner_value or '(no resolution)'}",
                "",
                "Roles:",
            ]
            for name, info in roles.items():
                lines.append(f"  {name:<20} {info['role'] or '?':<13} ({info['team'] or '?'}) "
                              f"- {'alive' if info['alive'] else 'eliminated'}")
            lines.append("")
            lines.append("How it unfolded:")
            lines.extend(f"  {line}" for line in self.log)
            fname.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass  # logging the match should never be able to crash the server

    # ------------------------------------------------------------------
    # Disconnects
    # ------------------------------------------------------------------
    def _handle_disconnect(self, sock: socket.socket) -> None:
        name = self._sock_to_name.get(sock)
        if not name or name not in self.players:
            return
        conn = self.players[name]
        conn.connected = False
        self._sock_to_name.pop(sock, None)
        if not self.started:
            del self.players[name]
            if self.host_name == name:
                self.host_name = next(iter(self.players), None)
            self._broadcast_lobby()
            self.announce(f"{name} left the lobby.")
            return
        self.announce(f"{name} disconnected.")
        if self.host_name == name:
            self.host_name = next((n for n, c in self.players.items() if c.connected), None)
            if self.host_name:
                self.announce(f"{self.host_name} is now the host.")
        # A disconnect never itself ends the game -- their next action just
        # defaults (see _collect_responses / the fallbacks in each phase),
        # and if they reconnect with the same name they resume their seat.
