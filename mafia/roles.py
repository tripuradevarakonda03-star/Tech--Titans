"""
Pure role and team definitions for Terminal Mafia -- no sockets, no
threads, no I/O of any kind. Kept separate from game.py specifically so
it can be unit-tested directly, the same way mafia/roles.py is tested in
the original iac-game-dev-8.0 project this structure is modeled on.
"""

from __future__ import annotations

from enum import Enum


class Team(str, Enum):
    HUNTERS = "Hunters"
    SURVIVORS = "Survivors"


class Role(str, Enum):
    VILLAGER = "Villager"
    SOLDIER = "Soldier"
    DETECTIVE = "Detective"
    SHAPESHIFTER = "Shapeshifter"


# The ROOT 36 "Terminal Mafia" problem statement specifies a fixed 5-seat
# table (2 Villagers, 1 Soldier, 1 Detective, 1 Shapeshifter) -- unlike a
# scaling role list, this game is not meant to grow with player count.
REQUIRED_PLAYERS = 5
MAX_DEATHS = 3  # Hunters win once this many players have died, total

ROLE_TEAM: dict[Role, Team] = {
    Role.VILLAGER: Team.SURVIVORS,
    Role.SOLDIER: Team.SURVIVORS,
    Role.DETECTIVE: Team.SURVIVORS,
    Role.SHAPESHIFTER: Team.HUNTERS,
}

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.VILLAGER: "No special power. Your only tools are your voice and your vote.",
    Role.SOLDIER: "Each night, shield one player (including yourself) from an attack.",
    Role.DETECTIVE: (
        "No special power -- you're the table's loudest voice of suspicion. "
        "You don't investigate or get any hidden information; you win by "
        "reading people and pushing the vote."
    ),
    Role.SHAPESHIFTER: "Each night, choose someone to eliminate. By day, blend in and deflect suspicion.",
}


def team_of(role: Role) -> Team:
    """The team a given role belongs to."""
    return ROLE_TEAM[role]


def role_distribution(num_players: int) -> list[Role]:
    """
    The fixed list of roles to deal for a table of `num_players`.

    Terminal Mafia's rules are specified for exactly REQUIRED_PLAYERS (5)
    seats -- this raises ValueError for anything else rather than trying
    to improvise a scaled distribution, since the problem statement's
    role balance (1 Shapeshifter, 1 Soldier, 1 Detective, 2 Villagers)
    was only ever designed and balanced for five.
    """
    if num_players != REQUIRED_PLAYERS:
        raise ValueError(
            f"Terminal Mafia is a fixed {REQUIRED_PLAYERS}-player game; got {num_players}."
        )
    return [Role.VILLAGER, Role.VILLAGER, Role.SOLDIER, Role.DETECTIVE, Role.SHAPESHIFTER]


def describe(role: Role) -> str:
    return ROLE_DESCRIPTIONS[role]
