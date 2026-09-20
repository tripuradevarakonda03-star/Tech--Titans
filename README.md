# Terminal Mafia

A local-hosted, multiplayer, terminal-based social deduction game (Mafia /
Among Us style) built for **ROOT 36, IIT Palakkad**.

One player hosts a game server on their machine; everyone else connects from
their own terminal -- either other windows on the same machine, or other
devices on the same LAN / mobile hotspot. No GUI, no cloud, no external
services: pure sockets and text.

## Requirements

- Python 3.9+ (standard library only -- **no `pip install` needed** to play),
  **or** the prebuilt executables in [`dist/`](dist) if you don't have Python
- All players on the same local network (or the same machine, for a solo test)

## Quick start (prebuilt executables)

No Python required. From `dist/`:

```
dist/terminal-mafia-server --port 5050
```

Everyone else:

```
dist/terminal-mafia-client <host-ip> 5050
```

Rebuild them yourself anytime with `pip install pyinstaller` and
`python -m PyInstaller --onefile server.py` (same for `client.py` /
`bot_client.py`) -- they're just packaged copies of the scripts below.

## Quick start (from source)

**1. Host starts the server** (pick any free port, e.g. 5050):

```
python server.py --port 5050
```

The server prints its own bind address and a ready-to-copy connect command.
Find the host machine's LAN IP yourself with `ipconfig` (Windows) /
`ifconfig` or `ip addr` (Mac/Linux) if you need it -- look for something like
`192.168.x.x`.

**2. Everyone else connects** from their own terminal:

```
python client.py <host-ip> 5050
```

Run `python client.py` with no arguments and it will try to auto-discover a
server on the local network/hotspot first, falling back to asking for the
host IP and port if nothing answers (some phone hotspots block this kind of
broadcast). On the same machine, just open more terminal windows and connect
to `127.0.0.1` instead of a LAN IP.

**3. Enter a name when prompted.** The first *human* to join is the **host**
(a bot can never end up hosting, even if bots joined first) and can type
`start` once ready.

**4. Play.** Prompts tell you exactly what to do each phase -- type a number
or a player's name.

### Solo testing without other humans

The host can add AI bot players right from their own client -- type
`bots <n>` in the lobby (e.g. `bots 4`) to fill empty seats. Typing `start`
with empty seats remaining auto-fills the rest with bots anyway, so this is
just for topping up early. A table with zero human players (all bots) starts
itself automatically, since no bot would ever type `start`.

Alternatively, start the server with bots already attached from the CLI:

```
python server.py --port 5050 --bots 4
```

### Options

```
python server.py [--port 5050] [--host 0.0.0.0] [--bots 0]
```

Terminal Mafia is a **fixed 5-player game** (see *How to play* below), so
unlike a scaling role list, there's no `--min-players` to configure --
`start` always fills the table to exactly five, one way or another.

## How to play

Each night, the Soldier and the Shapeshifter secretly submit an action. Each
day, the table discusses in an open chat, then votes to eliminate a suspect.

| Role             | Team      | Ability                                                                                                   |
| ---------------- | --------- | ----------------------------------------------------------------------------------------------------------- |
| **Villager** x2  | Survivors | No special power. Your only tools are your voice and your vote.                                            |
| **Soldier** x1   | Survivors | Each night, shield one player (including yourself) from an attack.                                          |
| **Detective** x1 | Survivors | No special power either -- the table's loudest voice of suspicion. You win by reading people, not evidence. |
| **Shapeshifter** x1 | Hunters | Each night, choose someone to eliminate. By day, blend in and deflect suspicion.                          |

Role counts are always exactly this 2/1/1/1 split -- Terminal Mafia doesn't
scale roles with table size the way some Mafia variants do, because the
ROOT 36 problem statement specifies a fixed 5-seat table.

**Voting.** Every living player secretly submits a vote; results are
revealed together once everyone's in (or the vote timer runs out). A tie
between the top vote-getters eliminates no one. Voting out the Shapeshifter
ends the game on the spot.

**Discussion isn't just free chat.** Type `accuse <name>` during the day to
publicly flag a suspect -- it updates a live suspicion tally broadcast to the
whole table, on top of ordinary chat.

**Last words.** A player voted out gets a short window to say something
before their role is revealed to everyone.

**The result of each round stays on screen for 10 seconds** before the next
night begins, so no one has to scramble to read what just happened.

**Win conditions**

- **Survivors win** the moment the Shapeshifter is voted out.
- **Hunters win** if the Shapeshifter survives until 3 total players have
  died (by night kill or day vote), whichever happens first.

**Reconnecting.** If you drop mid-game, reconnect with
`python client.py <host> <port>` and enter the *exact same name* you had
before -- you'll resume your seat, role, and alive/dead status instead of
being locked out or replaced.

## Architecture

```
server.py          CLI entry point for the host: parses args, spawns bots, runs GameServer
client.py           Terminal UI for a human player: renders server messages, relays typed input
bot_client.py       Same wire protocol as client.py, but auto-plays for testing/demos/auto-fill
mafia/
  protocol.py       Newline-delimited JSON message framing shared by server & every client
  discovery.py      UDP broadcast/reply so a client can auto-find a server on the LAN
  roles.py          Pure role definitions + the fixed 5-player distribution (no I/O, unit-testable)
  game.py           GameServer: connection handling + the night/day phase state machine
  colors.py         Dependency-free ANSI color helpers for the terminal UI
match_history/      One human-readable log file per completed match
```

**Networking model:** the server is authoritative. It accepts TCP
connections and spawns one lightweight reader thread per client; those
threads only ever push incoming messages onto a single thread-safe queue.
All game-state mutation (role assignment, phase transitions, vote tallying,
win checks) happens on one thread, so there's no locking to get wrong around
the actual game logic. Every prompt and every private message (a player's
own role) is addressed to one socket -- a client only ever receives what it's
entitled to see.

**Bots are just clients.** `bot_client.py` speaks the exact same protocol as
a human `client.py`; the server spawns it as an ordinary subprocess that
connects back over loopback. There is no special-cased "bot" code path
inside `GameServer` at all -- if the protocol looks right, it plays.

**Resilience:** a disconnect at any point (lobby, night action, discussion,
vote) is caught and handled gracefully -- the player is marked disconnected,
the table is notified, and if they were the host, host status transfers
automatically to another connected human. A missed night action or vote
(timeout, or a disconnect mid-decision) defaults sensibly rather than
stalling the game. Malformed or oversized input from a client is rejected
and the connection recovers instead of taking the server down.

## Tests

`mafia/roles.py` is pure logic (no sockets/threads), so it's unit-tested
directly. There's also a live integration suite that spins up a real
`GameServer` on a loopback socket and throws malformed JSON, oversized
payloads, unknown message types, abrupt disconnects, and duplicate names at
it -- confirming a broken or hostile client can never take the game down for
everyone else. It also plays a handful of complete games to `game_over` over
real sockets (including an all-bot table with real `bot_client.py`
subprocesses) to check the whole state machine end to end, not just its
pieces in isolation.

```
python -m unittest discover tests -v
```

## AI usage

Generative AI assistance (Claude) was used during development for code
generation, in line with the ROOT 36 rule book's AI tool policy. All logic
was authored, tested, and adapted specifically for this project during the
hackathon window.

## Known limitations

- No GUI/animations -- colored ANSI text only, by design (CLI-only requirement).
- Timed phases use fixed durations (`mafia/game.py`); tune `NIGHT_TIME`,
  `DAY_DISCUSS_TIME`, `DAY_VOTE_TIME`, `ROUND_RESULT_HOLD` for a faster or
  slower table.
- UDP discovery (`mafia/discovery.py`) is best-effort -- some phone hotspots
  and locked-down networks block broadcast traffic, so `client.py` always
  falls back to asking for a host/port manually.
