import unittest

from mafia.roles import (
    MAX_DEATHS,
    REQUIRED_PLAYERS,
    Role,
    Team,
    describe,
    role_distribution,
    team_of,
)


class TestRoleDistribution(unittest.TestCase):
    def test_five_players_gives_exact_counts(self):
        roles = role_distribution(5)
        self.assertEqual(len(roles), 5)
        self.assertEqual(roles.count(Role.VILLAGER), 2)
        self.assertEqual(roles.count(Role.SOLDIER), 1)
        self.assertEqual(roles.count(Role.DETECTIVE), 1)
        self.assertEqual(roles.count(Role.SHAPESHIFTER), 1)

    def test_rejects_any_other_table_size(self):
        for bad_count in (0, 1, 4, 6, 10):
            with self.assertRaises(ValueError):
                role_distribution(bad_count)

    def test_required_players_constant_matches_distribution_length(self):
        self.assertEqual(REQUIRED_PLAYERS, 5)
        self.assertEqual(len(role_distribution(REQUIRED_PLAYERS)), REQUIRED_PLAYERS)


class TestTeams(unittest.TestCase):
    def test_shapeshifter_is_the_only_hunter(self):
        for role in (Role.VILLAGER, Role.SOLDIER, Role.DETECTIVE):
            self.assertEqual(team_of(role), Team.SURVIVORS)
        self.assertEqual(team_of(Role.SHAPESHIFTER), Team.HUNTERS)

    def test_every_role_has_a_description(self):
        for role in Role:
            self.assertTrue(describe(role))

    def test_detective_description_explicitly_has_no_power(self):
        # Regression guard: the Detective was redesigned to have no
        # investigate ability -- just suspicion/accusation. Make sure a
        # future edit can't silently reintroduce an investigate power
        # without this test failing.
        text = describe(Role.DETECTIVE).lower()
        self.assertIn("no special power", text)


class TestMaxDeaths(unittest.TestCase):
    def test_max_deaths_is_three(self):
        self.assertEqual(MAX_DEATHS, 3)


if __name__ == "__main__":
    unittest.main()
