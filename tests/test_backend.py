import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from life_insurance_lab.backend.server import MAX_BODY_BYTES, make_server
from life_insurance_lab.backend.service import ExecutionError, Service
from life_insurance_lab.backend.storage import Conflict, Store
from life_insurance_lab.errors import SimulationLimitError
from life_insurance_lab.jsonio import dumps


MODEL = {'policy': {'term_months': 2, 'monthly_premium': 100, 'monthly_expense': 10,
          'acquisition_expense': 20, 'mortality_monthly': 0, 'lapse_monthly': 0,
          'valuation_interest_monthly': 0, 'sum_assured': 1000},
          'simulation': {'initial_policies': 3, 'acquisition_months': 0,
          'yule_rate_monthly': 0, 'starting_capital': 1000, 'asset_interest_monthly': 0,
          'capital_buffer': 0}}


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'lab.sqlite3'
        self.store = Store(self.path)
        self.service = Service(self.store)

    def tearDown(self):
        self.directory.cleanup()

    def test_edit_history_conflict_and_immutable_run_snapshot(self):
        saved = self.service.create_config({'name': "Student's baseline", 'kind': 'model', 'document': MODEL})
        outcome = self.service.execute('simulation', {'config_id': saved['id']})
        revised = saved['document']
        revised['policy']['monthly_premium'] = '200.00'
        updated = self.service.update_config(saved['id'], {'document': revised, 'expected_revision': 1})
        self.assertEqual(updated['revision'], 2)
        with self.assertRaises(Conflict):
            self.service.update_config(saved['id'], {'document': revised, 'expected_revision': 1})
        self.assertEqual(self.store.get_config(saved['id'], 1)['document']['policy']['monthly_premium'], '100.00')
        self.store.delete_config(saved['id'], 2)
        restarted = Store(self.path)
        run = restarted.get_run(outcome['id'])
        self.assertEqual(run['request']['config']['policy']['monthly_premium'], '100.00')
        self.assertEqual(run['request']['config_reference']['revision'], 1)
        self.assertEqual(run['result']['contract']['premium_paise'], 10000)
        self.assertEqual(run['status'], 'completed')
        with self.assertRaises(Conflict):
            restarted.finish_run(outcome['id'], 'completed', {})

    def test_persistence_is_optional(self):
        result = self.service.execute('simulation', {'config': MODEL, 'persist': False})
        self.assertIsNone(result['id'])
        self.assertFalse(result['persisted'])
        self.assertEqual(self.store.list_runs(), [])

    def test_limit_failure_is_saved_as_incomplete(self):
        with patch('life_insurance_lab.backend.service.simulate', side_effect=SimulationLimitError('budget exhausted')):
            with self.assertRaises(ExecutionError) as caught:
                self.service.execute('simulation', {'config': MODEL})
        saved = self.store.get_run(caught.exception.run_id)
        self.assertEqual(saved['status'], 'incomplete')
        self.assertIsNone(saved['result'])
        self.assertIn('budget', saved['error'])

    def test_orphaned_run_is_marked_interrupted(self):
        identifier = self.store.begin_run('simulation', {'config': MODEL})
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertEqual(self.store.get_run(identifier)['status'], 'interrupted')

    def test_compute_busy_and_wrong_reference_kind(self):
        self.service.compute_lock.acquire()
        try:
            with self.assertRaises(Conflict):
                self.service.execute('simulation', {'config': MODEL})
        finally:
            self.service.compute_lock.release()
        scenario = self.service.create_config({'kind': 'scenario', 'name': 'baseline', 'document': {}})
        with self.assertRaises(ValueError):
            self.service.execute('simulation', {'config_id': scenario['id']})


class HTTPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.directory.name)/'api.sqlite3', port=0, quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, method, path, body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        data = raw if raw is not None else (None if body is None else dumps(body).encode())
        actual_headers = {'Content-Type': 'application/json'} if data is not None else {}
        actual_headers.update(headers or {})
        connection.request(method, path, body=data, headers=actual_headers)
        response = connection.getresponse()
        text = response.read().decode()
        content_type = response.getheader('Content-Type')
        status = response.status
        connection.close()
        return status, json.loads(text) if 'application/json' in content_type else text

    def test_save_calculate_fetch_export_and_trace_over_http(self):
        status, health = self.request('GET', '/api/health')
        self.assertEqual((status, health['status']), (200, 'ok'))
        status, saved = self.request('POST', '/api/configs', {'name': 'demo', 'kind': 'model', 'document': MODEL})
        self.assertEqual(status, 201)
        status, result = self.request('POST', '/api/simulations', {'config_id': saved['id']})
        self.assertEqual(status, 200)
        identifier = result['id']
        self.assertTrue(result['persisted'])
        status, trace = self.request('GET', f'/api/runs/{identifier}/trace?month=0')
        self.assertTrue(trace['all_checks_pass'])
        status, csv = self.request('GET', f'/api/runs/{identifier}/ledger.csv')
        self.assertEqual(status, 200)
        self.assertIn('closing_cash_paise', csv)
        status, snapshot = self.request('GET', f'/api/runs/{identifier}')
        self.assertEqual(snapshot['request']['config']['policy']['monthly_premium'], '100.00')
        status, experiment = self.request('POST', '/api/experiments', {'config_id': saved['id'], 'paths': 3,
                         'capitals': [0, 1000], 'scenarios': [{'name': 'baseline'}]})
        self.assertEqual(status, 200)
        self.assertEqual(len(experiment['result']['cells']), 2)
        status, benchmark = self.request('POST', '/api/benchmarks', {'config_id': saved['id'], 'paths': 3})
        self.assertEqual(status, 200)
        self.assertEqual(benchmark['result']['fixed_cohort'][0]['active']['sample_mean'], 3)
        status, quote = self.request('POST', '/api/quote', {'config': {'policy': {
            'pricing_mode': 'benefit_to_premium', 'sum_assured': 1000000}}})
        self.assertEqual(status, 200)
        self.assertFalse(quote['persisted'])
        self.assertGreater(quote['result']['contract']['premium_paise'], 100000)

    def test_invalid_inputs_and_cross_origin_are_rejected(self):
        for body in ({'config': {'policy': {'mortality_monthly': 2}}}, {'paths': 1}, {'persist': 'false'}):
            self.assertEqual(self.request('POST', '/api/simulations', body)[0], 422)
        self.assertEqual(self.request('POST', '/api/quote', raw=b'{"config":{},"config":{}}')[0], 422)
        self.assertEqual(self.request('POST', '/api/quote', body={}, headers={'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('GET', '/api/health', headers={'Host': 'malicious.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/quote', body={}, headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/quote', raw=b'{}', headers={'Content-Length': str(MAX_BODY_BYTES+1)})[0], 413)
        self.assertEqual(self.request('GET', '/api/configs?limit=1000')[0], 422)

    def test_api_revision_conflicts_and_delete_retain_results(self):
        _, saved = self.request('POST', '/api/configs', {'name': 'edit', 'document': MODEL})
        _, run = self.request('POST', '/api/simulations', {'config_id': saved['id']})
        edit = {'document': saved['document'], 'expected_revision': 1, 'name': 'renamed'}
        self.assertEqual(self.request('PUT', '/api/configs/'+saved['id'], edit)[0], 200)
        self.assertEqual(self.request('PUT', '/api/configs/'+saved['id'], edit)[0], 409)
        self.assertEqual(self.request('DELETE', '/api/configs/'+saved['id'], {'expected_revision': 1})[0], 409)
        self.assertEqual(self.request('DELETE', '/api/configs/'+saved['id'], {'expected_revision': 2})[0], 200)
        self.assertEqual(self.request('GET', '/api/configs/'+saved['id'])[0], 404)
        self.assertEqual(self.request('GET', '/api/runs/'+run['id'])[1]['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
