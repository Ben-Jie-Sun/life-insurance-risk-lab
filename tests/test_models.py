import math
import random
import unittest

from life_insurance_lab.errors import ModelError, SimulationLimitError
from life_insurance_lab.models.policy import advance, transition_matrix
from life_insurance_lab.models.yule import issue_schedule, moments


class YuleTests(unittest.TestCase):
    def test_closed_form_moments(self):
        mean, variance = moments(3, math.log(2), 1)
        self.assertAlmostEqual(mean, 6)
        self.assertAlmostEqual(variance, 6)

    def test_zero_boundaries(self):
        rng = random.Random(1)
        self.assertEqual(issue_schedule(0, .5, 4, rng, 100), [0, 0, 0, 0, 0])
        self.assertEqual(issue_schedule(4, 0, 3, rng, 4), [4, 0, 0, 0])
        self.assertEqual(issue_schedule(4, .5, 0, rng, 4), [4])
        self.assertEqual(moments(0, 1000, 1000), (0, 0))

    def test_computational_cap_does_not_clip_population(self):
        class FixedWait:
            def expovariate(self, rate):
                return .1
        with self.assertRaises(SimulationLimitError):
            issue_schedule(1, .5, 1, FixedWait(), 2)

    def test_seeded_sample_matches_known_geometric_law(self):
        # Independent analytic target: P(N=1)=1/2, E[N]=2 at lambda*t=log 2.
        rng = random.Random(519)
        samples = [sum(issue_schedule(1, math.log(2), 1, rng, 1000)) for _ in range(5000)]
        self.assertAlmostEqual(sum(samples) / len(samples), 2, delta=.08)
        self.assertAlmostEqual(samples.count(1) / len(samples), .5, delta=.025)

    def test_invalid_rate(self):
        with self.assertRaises(ModelError):
            issue_schedule(1, -1, 3, random.Random(1), 100)


class PolicyTests(unittest.TestCase):
    def test_matrix_rows_and_example(self):
        matrix = transition_matrix(.001, .02)
        for row in matrix:
            self.assertTrue(all(0 <= x <= 1 for x in row))
            self.assertAlmostEqual(sum(row), 1)
        for actual, expected in zip(matrix[0], (.97902, .01998, .001)):
            self.assertAlmostEqual(actual, expected)

    def test_death_precedes_lapse(self):
        self.assertEqual(advance(10, 1, 1, random.Random(0), random.Random(1)), (0, 10, 0))
        self.assertEqual(advance(10, 0, 1, random.Random(0), random.Random(1)), (0, 0, 10))

    def test_conservation_over_many_draws(self):
        deaths, lapses = random.Random(13), random.Random(14)
        for n in range(100):
            active, d, l = advance(n, .2, .3, deaths, lapses)
            self.assertEqual(active + d + l, n)
            self.assertGreaterEqual(min(active, d, l), 0)
