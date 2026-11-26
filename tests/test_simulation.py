from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from life_insurance_lab.config import from_dict, load_config
from life_insurance_lab.errors import ModelError, SimulationLimitError
from life_insurance_lab.experiments import compare_lapse
from life_insurance_lab.reporting import write_result
from life_insurance_lab.simulation import simulate


def simple_config(**overrides):
    policy = dict(
        term_months=3, monthly_premium=100, monthly_expense=10,
        acquisition_expense=20, mortality_monthly=0, lapse_monthly=0,
        valuation_interest_monthly=0, target_epv_margin=0, sum_assured=1000
    )
    policy.update(overrides)
    return from_dict({
        "policy": policy,
        "simulation": dict(initial_policies=5, acquisition_months=0,
                           yule_rate_monthly=0, starting_capital=10000,
                           asset_interest_monthly=0, capital_buffer=0)
    })


class ProjectionTests(unittest.TestCase):
    def test_exact_expiry_and_accounting_without_random_events(self):
        r = simulate(simple_config())
        # Five policies, three premiums each, monthly cost 10, initial cost 20.
        self.assertEqual(r.summary["total_premiums_paise"], 150000)
        self.assertEqual(r.summary["total_expenses_paise"], 25000)
        self.assertEqual(r.summary["economic_surplus_paise"], 125000)
        self.assertEqual(r.summary["expired"], 5)
        self.assertEqual(r.summary["active_at_end"], 0)

    def test_certain_death_collects_only_one_premium_and_one_claim(self):
        r = simulate(simple_config(mortality_monthly=1, lapse_monthly=1))
        self.assertEqual(r.summary["deaths"], 5)
        self.assertEqual(r.summary["lapses"], 0)
        self.assertEqual(r.summary["total_premiums_paise"], 50000)
        self.assertEqual(r.summary["total_claims_paise"], 500000)
        self.assertEqual(r.monthly[1]["premiums_paise"], 0)

    def test_certain_lapse_and_final_month_expiry(self):
        r = simulate(simple_config(lapse_monthly=1))
        self.assertEqual(r.summary["lapses"], 5)
        self.assertEqual(r.summary["total_premiums_paise"], 50000)
        r = simulate(simple_config(term_months=1, lapse_monthly=1))
        self.assertEqual(r.summary["expired"], 5)
        self.assertEqual(r.summary["lapses"], 0)

    def test_shortfall_tracks_liability_without_negative_cash(self):
        c = simple_config(term_months=1, mortality_monthly=1)
        c = replace(c, simulation=replace(c.simulation, starting_capital_paise=0))
        r = simulate(c)
        # 500 premium less 150 expense = 350 cash available for a 5000 claim.
        self.assertEqual(r.summary["total_claims_paid_paise"], 35000)
        self.assertEqual(r.summary["unpaid_claims_paise"], 465000)
        self.assertEqual(r.summary["closing_cash_paise"], 0)
        self.assertEqual(r.summary["economic_surplus_paise"], -465000)
        self.assertTrue(r.summary["payment_shortfall_ever"])

    def test_unpaid_expenses_are_not_erased(self):
        c = simple_config(term_months=1, acquisition_expense=200, monthly_expense=0)
        c = replace(c, simulation=replace(c.simulation, starting_capital_paise=0))
        r = simulate(c)
        self.assertEqual(r.summary["unpaid_expenses_paise"], 50000)
        self.assertEqual(r.summary["net_assets_paise"], -50000)

    def test_stop_new_issues_after_shortfall(self):
        c = simple_config(term_months=1, mortality_monthly=1)
        c = replace(c, simulation=replace(c.simulation, initial_policies=1,
                                         acquisition_months=2, starting_capital_paise=0))
        with patch("life_insurance_lab.simulation.issue_schedule", return_value=[1, 2, 0]):
            r = simulate(c)
        self.assertEqual(r.summary["policies_issued"], 1)
        self.assertEqual(r.summary["candidates_not_issued"], 2)
        self.assertEqual(r.summary["active_at_end"], 0)

    def test_zero_population_and_full_runoff(self):
        c = simple_config()
        c = replace(c, simulation=replace(c.simulation, initial_policies=0))
        r = simulate(c)
        self.assertEqual(r.summary["policies_issued"], 0)
        self.assertEqual(r.summary["total_claims_paise"], 0)

    def test_extreme_asset_growth_is_incomplete_not_a_valid_result(self):
        for rate in (1e20, 1e100):
            c = simple_config()
            c = replace(c, simulation=replace(c.simulation, asset_rate_monthly=rate))
            with self.subTest(rate=rate), self.assertRaises(SimulationLimitError):
                simulate(c)

    def test_seed_reproduction_and_policy_conservation(self):
        c = from_dict({})
        first, second = simulate(c), simulate(c)
        self.assertEqual(first.as_dict(), second.as_dict())
        s = first.summary
        self.assertEqual(s["policies_issued"], s["deaths"] + s["lapses"] + s["expired"])

    def test_comparison_freezes_benefit_and_reports_uncertainty(self):
        c = simple_config(mortality_monthly=.01)
        comparison = compare_lapse(c, paths=3)
        self.assertEqual(comparison["fixed_sum_assured_paise"], c.policy.sum_assured_paise)
        self.assertEqual(len(comparison["scenarios"]), 3)
        for row in comparison["scenarios"]:
            self.assertEqual(row["paths"], 3)
            self.assertGreater(row["payment_shortfall_wilson_95"][1], 0)

    def test_incomplete_comparison_is_rejected(self):
        with patch("life_insurance_lab.experiments.simulate",
                   side_effect=SimulationLimitError("limit")):
            with self.assertRaises(SimulationLimitError):
                compare_lapse(simple_config(), 2)

    def test_report_preserves_machine_readable_results_and_escapes_text(self):
        c = simple_config()
        c = replace(c, policy=replace(c.policy, name="<script>unsafe</script>"))
        with tempfile.TemporaryDirectory() as directory:
            path = write_result(simulate(c), directory)
            html = path.read_text(encoding="utf-8")
            self.assertNotIn("<script>unsafe</script>", html)
            self.assertIn("&lt;script&gt;", html)
            payload = json.loads((Path(directory) / "result.json").read_text())
            self.assertEqual(payload["summary"]["expired"], 5)


class InputTests(unittest.TestCase):
    def test_invalid_inputs(self):
        for raw in (
            {"polciy": {}},
            {"policy": {"mortality_monthly": 1.1}},
            {"policy": {"term_months": True}},
            {"policy": {"monthly_premium": -1}},
            {"policy": {"monthly_premium": "0.001"}},
            {"policy": {"mortality_monthly": [.1]}},
            {"simulation": {"initial_policies": -1}},
            {"policy": {"valuation_interest_monthly": -1}},
        ):
            with self.subTest(raw=raw), self.assertRaises(ModelError):
                from_dict(raw)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "bad.json"
            p.write_text('{"policy":{"mortality_monthly":NaN}}')
            with self.assertRaises(ModelError):
                load_config(p)
