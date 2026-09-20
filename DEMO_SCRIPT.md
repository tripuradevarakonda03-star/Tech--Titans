# Demo script (3-5 minutes)

A suggested walkthrough for the submission video. Times are approximate --
adjust `NIGHT_TIME` / `DAY_DISCUSS_TIME` / `DAY_VOTE_TIME` in
`mafia/game.py` down if you want a snappier recording.

## 0:00 -- Intro (15s)

- "This is Terminal Mafia, our submission for Terminal Mafia at ROOT 36."
- One line on the concept: a hidden Shapeshifter among five players; the
  rest win by finding and voting them out before three players die.

## 0:15 -- Start the server (20s)

On the host's machine:

```
python server.py --port 5050
```

Point out the printed connect command and that this is a real TCP server on
the LAN -- no cloud, nothing installed beyond Python.

## 0:35 -- Everyone connects (30s)

Cut to 2-4 other terminals (other machines, or just other windows on the
same laptop connecting to `127.0.0.1`), each running:

```
python client.py <host-ip> 5050
```

Show each player typing a name and appearing in the lobby list. Mention
that any empty seats auto-fill with AI bots the moment the host types
`start` -- good for a solo test recording too.

## 1:05 -- Roles dealt (20s)

Host types `start`. Cut to one or two players' screens showing their
private role reveal (e.g. one Villager screen, and the Shapeshifter's
screen) -- this demonstrates that role information is genuinely private
per-socket, not just hidden by UI convention.

## 1:25 -- A night phase (30s)

Show the Soldier picking a protect target and the Shapeshifter picking a
kill target on their own screens. Narrate: "these two are the only ones
prompted right now -- everyone else is just waiting."

## 1:55 -- Day phase: reveal, discuss, vote (60-90s)

- The death (or "everyone survived") announcement landing on every screen
  at once.
- A player typing `accuse <name>` and the live suspicion tally updating on
  everyone's screen.
- A couple of chat lines, including a bot player chiming in with its own
  discussion line.
- The vote itself, then the tally and the round's result.
- Point out the 10-second hold before the next round begins.

## 3:00 -- Fast-forward to game over (30s)

Either let a couple more rounds play out on camera, or cut to the final
round. Show the `GAME OVER` screen: winning team, and the full role reveal
for every player (including the ones already eliminated).

## 3:30 -- Resilience beat, optional (20s)

Kill one player's terminal mid-game (Ctrl+C or close the window) to show
the rest of the table gets notified and play continues -- then reconnect
that same client with the same name to show it resumes the same seat and
role instead of being locked out.

## 3:50 -- Close (10s)

One line on the architecture: authoritative server, one thread per
connection, bots are just ordinary clients over the same protocol -- and a
mention of the test suite (`python -m unittest discover tests -v`) as
evidence it's been exercised against hostile/malformed input, not just
happy-path manual testing.
