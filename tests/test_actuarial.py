from dataclasses import replace
from itertools import product
import unittest

from life_insurance_lab.actuarial import factors, quote, reserve_schedule
from life_insurance_lab.config import from_dict
from life_insurance_lab.errors import ModelError


class ValuationTests(unittest.TestCase):
    def test_one_month_hand_calculation(self):
        p = from_dict({"policy": {
            "term_months": 1, "monthly_premium": 1000,
            "monthly_expense": 100, "acquisition_expense": 50,
            "mortality_monthly": .1, "lapse_monthly": .9,
            "valuation_interest_monthly": .01, "target_epv_margin": 100
        }}).policy
        q = quote(p)
        # 1000 = 150 + 100 + .1*B/1.01; B=7575 rupees.
        self.assertLessEqual(abs(q.selected_benefit_paise - 757500), 1)
        self.assertGreaterEqual(q.expected_margin_paise + 1e-6, 10000)
        self.assertAlmostEqual(reserve_schedule(p, q.selected_benefit_paise)[0],
                               -q.expected_margin_paise, places=6)

    def test_recursion_against_enumeration_of_all_exit_paths(self):
        p = from_dict({"policy": {
            "term_months": 3, "monthly_premium": 200,
            "monthly_expense": 10, "acquisition_expense": 20,
            "mortality_monthly": [.1, .2, .3],
            "lapse_monthly": [.2, .3, .1],
            "valuation_interest_monthly": .02, "sum_assured": 5000
        }}).policy
        benefit = p.sum_assured_paise
        v = 1 / 1.02
        expected = 0
        # Independent reference: enumerate S, L, D outcomes at every period.
        for events in product("SLD", repeat=3):
            prob, cashflow, active = 1.0, 0.0, True
            for k, event in enumerate(events):
                if not active:
                    # A canonical S placeholder avoids counting an exited path repeatedly.
                    if event != "S":
                        prob = 0
                    continue
                expense = 1000 + (2000 if k == 0 else 0)
                cashflow += (expense - 20000) * v**k
                if event == "D":
                    prob *= p.mortality[k]
                    cashflow += benefit * v**(k+1)
                    active = False
                elif event == "L":
                    prob *= (1-p.mortality[k]) * p.lapse[k]
                    active = False
                else:
                    prob *= (1-p.mortality[k]) * (1-p.lapse[k])
            expected += prob * cashflow
        self.assertAlmostEqual(reserve_schedule(p, benefit)[0], expected, places=6)

    def test_no_lapse_recovers_survival_factors(self):
        p = from_dict({"policy": {"term_months": 3, "lapse_monthly": 0}}).policy
        a, b, _ = factors(p)
        v = 1 / (1 + p.valuation_rate_monthly)
        self.assertAlmostEqual(a, sum((v*.999)**k for k in range(3)))
        self.assertAlmostEqual(b, sum(v**(k+1) * .999**k * .001 for k in range(3)))

    def test_zero_mortality_requires_explicit_benefit(self):
        p = from_dict({"policy": {"mortality_monthly": 0}}).policy
        with self.assertRaises(ModelError):
            quote(p)
        q = quote(replace(p, sum_assured_paise=10000))
        self.assertEqual(q.benefit_factor, 0)
        self.assertIsNone(q.candidate_benefit_paise)

    def test_insufficient_premium_rejects_auto_cover(self):
        p = from_dict({"policy": {"monthly_premium": 1}}).policy
        with self.assertRaises(ModelError):
            quote(p)
