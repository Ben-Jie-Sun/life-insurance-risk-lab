import csv
import io
import json
import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from life_insurance_lab.backend.service import Service, ExecutionError
from life_insurance_lab.backend.server import make_server
from life_insurance_lab.backend.storage import Store
from life_insurance_lab.config import from_dict
from life_insurance_lab.errors import ModelError, SimulationLimitError
from life_insurance_lab.monte_carlo import run_monte_carlo
from life_insurance_lab.simulation import simulate

MODEL = {'policy': {'term_months': 3, 'monthly_premium': 100, 'monthly_expense': 10,
                   'acquisition_expense': 20, 'mortality_monthly': .1, 'lapse_monthly': .05,
                   'valuation_interest_monthly': 0, 'sum_assured': 1000},
         'simulation': {'initial_policies': 4, 'acquisition_months': 2, 'yule_rate_monthly': .2,
                        'starting_capital': 100, 'asset_interest_monthly': 0, 'capital_buffer': 0,
                        'seed': 83}}

class MonteCarloTests(unittest.TestCase):
    def test_ensemble_matches_existing_engine_and_replays(self):
        config=from_dict(MODEL)
        r=run_monte_carlo(config, 8)
        self.assertEqual(r, run_monte_carlo(config, 8))
        singles=[simulate(config, 83+i) for i in range(8)]
        self.assertEqual(r['summary']['payment_shortfall']['events'],sum(s.summary['payment_shortfall_ever'] for s in singles))
        self.assertEqual(r['summary']['economic_surplus_paise']['mean'],sum(s.summary['economic_surplus_paise'] for s in singles)/8)
        for i,row in enumerate(r['monthly']):
            self.assertEqual(row['active_close']['mean'],sum(s.monthly[i]['active_close'] for s in singles)/8)
        self.assertEqual(r['yule_benchmark']['simulated_mean'],sum(s.summary['candidates_generated'] for s in singles)/8)
        self.assertEqual(r['convergence'][-1]['shortfall'],r['summary']['payment_shortfall'])
        self.assertEqual(run_monte_carlo(from_dict(r['replay_config']),8),r)

    def test_deterministic_case_and_zero_failure_interval(self):
        raw=json.loads(json.dumps(MODEL));raw['policy'].update(mortality_monthly=0,lapse_monthly=0)
        raw['simulation'].update(yule_rate_monthly=0,starting_capital=10000)
        r=run_monte_carlo(from_dict(raw),20)
        self.assertEqual(r['summary']['economic_surplus_paise']['mean'],4*(3*(100-10)-20)*100)
        self.assertEqual(r['summary']['economic_surplus_paise']['standard_error'],0)
        self.assertEqual(r['summary']['payment_shortfall']['events'],0)
        self.assertGreater(r['summary']['payment_shortfall']['wilson_95'][1],0)
        self.assertGreater(r['summary']['payment_shortfall']['zero_events_one_sided_95_upper'],0)
        self.assertEqual(r['monthly'][-1]['active_close']['mean'],0)

    def test_certain_claim_causes_shortfall_in_every_path(self):
        raw=json.loads(json.dumps(MODEL));raw['policy']['mortality_monthly']=1
        raw['simulation'].update(yule_rate_monthly=0,starting_capital=0)
        r=run_monte_carlo(from_dict(raw),10)
        self.assertEqual(r['summary']['payment_shortfall']['estimate'],1)
        self.assertEqual(r['monthly'][0]['cumulative_shortfall_fraction'],1)
        self.assertEqual(r['summary']['policies_issued']['mean'],4)

    def test_bounds_and_failed_path_are_not_omitted(self):
        c=from_dict(MODEL)
        for n in (1,True,1001):
            with self.assertRaises(ModelError):run_monte_carlo(c,n)
        with patch('life_insurance_lab.monte_carlo.MAX_ENSEMBLE_OBSERVATIONS',2):
            with self.assertRaises(SimulationLimitError):run_monte_carlo(c,2)
        with patch('life_insurance_lab.monte_carlo.simulate',side_effect=[simulate(c),SimulationLimitError('guard')]):
            with self.assertRaisesRegex(SimulationLimitError,'2/2; no paths were discarded'):run_monte_carlo(c,2)

    def test_persisted_snapshot_and_incomplete_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=Service(Store(Path(tmp)/'lab.db'))
            outcome=service.execute('monte_carlo',{'config':MODEL,'paths':5})
            saved=service.store.get_run(outcome['id'])
            self.assertEqual(saved['result'],json.loads(json.dumps(outcome['result'])))
            replay=Service().execute('monte_carlo',{'config':saved['request']['config'],'scenario':saved['request']['scenario'],'paths':5,'persist':False})
            self.assertEqual(json.loads(json.dumps(replay['result'])),saved['result'])
            with patch('life_insurance_lab.monte_carlo.simulate',side_effect=SimulationLimitError('guard')):
                with self.assertRaises(ExecutionError) as e:service.execute('monte_carlo',{'config':MODEL,'paths':5})
            self.assertEqual(service.store.get_run(e.exception.run_id)['status'],'incomplete')
            self.assertIsNone(service.store.get_run(e.exception.run_id)['result'])

    def test_http_dashboard_monte_carlo_and_csv_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(Path(tmp)/'lab.db',port=0,quiet=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def req(method,path,body=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                conn.request(method,path,None if body is None else json.dumps(body),{'Content-Type':'application/json'})
                response=conn.getresponse();code=response.status;data=response.read().decode();conn.close();return code,data
            try:
                code,html=req('GET','/');self.assertEqual(code,200);self.assertIn('Run Monte Carlo',html)
                code,js=req('GET','/app.js');self.assertEqual(code,200);self.assertIn('run(kind)',js)
                code,data=req('POST','/api/monte-carlo',{'config':MODEL,'paths':5});self.assertEqual(code,200)
                saved=json.loads(data);identifier=saved['id']
                for resource,length in [('bands.csv',5),('paths.csv',5)]:
                    code,data=req('GET',f'/api/runs/{identifier}/{resource}');self.assertEqual(code,200)
                    self.assertEqual(len(list(csv.DictReader(io.StringIO(data)))),length)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
