from dataclasses import replace
from decimal import Decimal
import math
import random
import unittest
from unittest.mock import patch

from life_insurance_lab.actuarial import quote
from life_insurance_lab.benchmarks import benchmark
from life_insurance_lab.config import from_dict
from life_insurance_lab.errors import ModelError
from life_insurance_lab.experiments import run_experiment
from life_insurance_lab.jsonio import dumps, loads
from life_insurance_lab.scenarios import Scenario, draw_return, from_dict as scenario_from_dict
from life_insurance_lab.simulation import simulate
from life_insurance_lab.traces import explain_month


def small():
    return from_dict({'policy': {'term_months': 3, 'monthly_premium': 100,
                      'monthly_expense': 10, 'acquisition_expense': 20,
                      'mortality_monthly': .01, 'lapse_monthly': .02,
                      'valuation_interest_monthly': 0, 'target_epv_margin': 5,
                      'sum_assured': 1000},
                      'simulation': {'initial_policies': 10, 'acquisition_months': 2,
                      'yule_rate_monthly': .2, 'starting_capital': 10000,
                      'asset_interest_monthly': 0, 'capital_buffer': 0}})


class PricingModeTests(unittest.TestCase):
    def test_reverse_price_independent_hand_calculation(self):
        # One month: premium = .1*5000 + 10+20 expenses + 70 margin = 600.
        config = from_dict({'policy': {'pricing_mode': 'benefit_to_premium',
               'sum_assured': 5000, 'term_months': 1, 'monthly_expense': 10,
               'acquisition_expense': 20, 'mortality_monthly': .1,
               'valuation_interest_monthly': 0, 'target_epv_margin': 70}})
        pricing = quote(config.policy)
        self.assertEqual(pricing.selected_premium_paise, 60000)
        self.assertEqual(pricing.selected_benefit_paise, 500000)
        self.assertAlmostEqual(pricing.expected_margin_paise, 7000)
        result = simulate(config)
        self.assertEqual(result.monthly[0]['premiums_paise'], 100*60000)
        self.assertEqual(result.contract['premium_paise'], 60000)

    def test_reverse_rounds_up_a_fraction_of_a_paisa(self):
        config = from_dict({'policy': {'pricing_mode': 'benefit_to_premium',
               'sum_assured': '100.01', 'term_months': 1, 'monthly_expense': 0,
               'acquisition_expense': 0, 'mortality_monthly': .01,
               'valuation_interest_monthly': 0, 'target_epv_margin': 0}})
        self.assertEqual(quote(config.policy).selected_premium_paise, 101)

    def test_explicit_modes_reject_ambiguous_inputs(self):
        for policy in ({'pricing_mode': 'benefit_to_premium'},
                       {'pricing_mode': 'benefit_to_premium', 'sum_assured': 1000, 'monthly_premium': 10},
                       {'pricing_mode': 'premium_to_benefit', 'sum_assured': 1000},
                       {'pricing_mode': 'assess'}, {'pricing_mode': 'unknown'}):
            with self.subTest(policy=policy), self.assertRaises(ModelError):
                from_dict({'policy': policy})

    def test_complete_input_roundtrip(self):
        config = from_dict({'policy': {'pricing_mode': 'benefit_to_premium', 'sum_assured': '1000000.01'}})
        self.assertEqual(from_dict(loads(dumps(config.to_input_dict()))), config)
        raw = loads('{"amount":90071992547409.91}')
        self.assertEqual(loads(dumps(raw))['amount'], Decimal('90071992547409.91'))
        with self.assertRaises(ModelError):
            loads('{"seed":1,"seed":2}')

    def test_oversized_money_and_json_numbers_are_validation_errors(self):
        for value in ('1e999999999', '10000000000000000.01'):
            with self.assertRaises(ModelError):
                from_dict({'policy': {'monthly_premium': value}})
        with self.assertRaises(ModelError):
            loads('{"seed":'+'9'*100+'}')


class ScenarioTests(unittest.TestCase):
    def test_zero_change_reproduces_baseline(self):
        config = from_dict({})
        baseline = simulate(config)
        explicit = simulate(config, scenario=scenario_from_dict({'name': 'baseline', 'return_volatility_monthly': 0}))
        self.assertEqual(baseline.as_dict(), explicit.as_dict())
        self.assertEqual(baseline.summary['policies_issued'], 163)
        self.assertEqual(baseline.summary['closing_cash_paise'], 794382106)

    def test_shock_does_not_reprice_contract(self):
        config = from_dict({})
        baseline = simulate(config)
        shock = simulate(config, scenario=Scenario(name='mortality', mortality_multiplier=5))
        self.assertEqual(baseline.contract, shock.contract)
        self.assertEqual(baseline.pricing, shock.pricing)
        for row in shock.monthly:
            self.assertEqual(row['claims_incurred_paise'], row['deaths']*baseline.contract['benefit_paise'])

    def test_calendar_shock_reaches_two_different_cohort_durations(self):
        config = small()
        config = replace(config, policy=replace(config.policy, mortality=(.01, .5, 0)))
        scenario = scenario_from_dict({'name': 'calendar shock', 'events': [
            {'start_month': 1, 'end_month': 2, 'mortality_multiplier': 2}]})
        with patch('life_insurance_lab.simulation.issue_schedule', return_value=[2, 1, 0]), \
             patch('life_insurance_lab.simulation.advance', side_effect=lambda n, q, l, *rng: (n, 0, 0)):
            result = simulate(config, scenario=scenario)
        row = result.monthly[1]
        self.assertAlmostEqual(row['mortality_probability_min'], .0199)
        self.assertAlmostEqual(row['mortality_probability_max'], .75)
        self.assertEqual(result.monthly[0]['mortality_multiplier'], 1)
        self.assertEqual(result.monthly[2]['mortality_multiplier'], 1)

    def test_event_validation_and_exclusive_end(self):
        invalid = [
            {'events': [{'start_month': 1, 'end_month': 1, 'mortality_multiplier': 2}]},
            {'events': [{'start_month': 1, 'end_month': 3, 'lapse_monthly': .1},
                        {'start_month': 2, 'end_month': 4, 'lapse_monthly': .2}]},
            {'mortality_multiplier': 0}, {'return_volatility_monthly': -1},
            {'asset_return_monthly': -1}, {'unknown': 2},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ModelError):
                scenario_from_dict(value)
        scenario = scenario_from_dict({'events': [{'start_month': 2, 'end_month': 4, 'lapse_monthly': 1}]})
        self.assertEqual(scenario.at(3, 0)['lapse_monthly'], 1)
        self.assertIsNone(scenario.at(4, 0)['lapse_monthly'])
        with self.assertRaises(ModelError):
            scenario.validate(3)

    def test_random_returns_preserve_mean_and_zero_volatility(self):
        self.assertEqual(draw_return(.003, 0, random.Random(1)), .003)
        rng = random.Random(10)
        returns = [draw_return(.003, .05, rng) for _ in range(20000)]
        self.assertTrue(all(value > -1 for value in returns))
        se = 1.003*math.sqrt(math.expm1(.05**2)/len(returns))
        self.assertLess(abs(sum(returns)/len(returns)-.003), 5*se)
        scenario = Scenario(name='random', return_volatility_monthly=.03)
        self.assertEqual(simulate(small(), scenario=scenario).as_dict(), simulate(small(), scenario=scenario).as_dict())

    def test_trace_reconciles_baseline_and_unpaid_obligations(self):
        for config in (small(), from_dict({'policy': {'term_months': 1, 'mortality_monthly': 1,
                       'sum_assured': 100000}, 'simulation': {'initial_policies': 1,
                       'acquisition_months': 0, 'starting_capital': 0}})):
            result = simulate(config).as_dict()
            for month in range(len(result['monthly'])):
                self.assertTrue(explain_month(result, month)['all_checks_pass'])


class ExperimentTests(unittest.TestCase):
    def test_grid_keeps_contract_and_valuation_basis_fixed(self):
        data = run_experiment(small(), [Scenario(), Scenario(name='stress', mortality_multiplier=2)],
                              [0, 1000000], paths=5)
        self.assertEqual(len(data['cells']), 4)
        self.assertEqual(data['fixed_sum_assured_paise'], 100000)
        self.assertEqual(data['reserve_basis'], 'fixed_original_pricing_assumptions')
        for row in data['cells']:
            self.assertEqual(len(row['path_metrics']), 5)
            self.assertGreaterEqual(row['median_surplus_paise'], row['surplus_p05_paise'])
            self.assertGreater(row['payment_shortfall_wilson_95'][1], 0)

    def test_benchmark_matches_certain_death_exactly(self):
        config = small()
        config = replace(config, policy=replace(config.policy, mortality=(1, 1, 1)))
        data = benchmark(config, paths=3)
        first = data['fixed_cohort'][0]
        self.assertEqual(first['active']['expected'], 10)
        self.assertEqual(first['claims_incurred_paise']['expected'], 1000000)
        self.assertEqual(first['claims_incurred_paise']['sample_mean'], 1000000)
        self.assertEqual(data['fixed_cohort'][1]['active']['sample_mean'], 0)
        self.assertAlmostEqual(data['cohort_margin_epv_paise']['expected'], data['cohort_margin_epv_paise']['sample_mean'])

    def test_work_and_shape_limits(self):
        for capitals, paths in (([0, 0], 10), ([0], 0), ([0], 1001)):
            with self.assertRaises(ModelError):
                run_experiment(small(), [Scenario()], capitals, paths)


if __name__ == '__main__':
    unittest.main()
