"""Reproduce all numerical results in the focused paper; no optional dependencies."""
from pathlib import Path
import sys,json,time,hashlib
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from life_insurance_lab.config import load_config
from life_insurance_lab.scenarios import load_scenario,Scenario
from life_insurance_lab.monte_carlo import run_monte_carlo,write_monte_carlo
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
 config=load_config(ROOT/'examples/baseline.json')
 cases=[('baseline',config,Scenario()),('low_capital',replace(config,simulation=replace(config.simulation,starting_capital_paise=100000000)),Scenario()),('mortality_shock',config,load_scenario(ROOT/'examples/scenarios/mortality_shock.json')),('combined_stress',config,load_scenario(ROOT/'examples/scenarios/combined_stress.json'))]
 summary={}
 for name,c,s in cases:
  start=time.perf_counter();result=run_monte_carlo(c,1000,s)
  write_monte_carlo(result,ROOT/'paper/results'/name)
  summary[name]={'summary':result['summary'],'yule_benchmark':result['yule_benchmark'],'pricing':result['pricing'],'paths':result['paths'],'seed_start':result['seed_start'],'seed_end':result['seed_end'],'seconds':time.perf_counter()-start}
  print(name,json.dumps(summary[name]),flush=True)
 (ROOT/'paper/results/summary.json').write_text(json.dumps(summary,indent=2))

 sources=list((ROOT/'life_insurance_lab').rglob('*.py'))+list((ROOT/'examples').rglob('*.json'))
 manifest={'python':sys.version,'application':'0.3.0','paths_per_case':1000,'seed_range':[2026,3025],
           'cases':list(summary),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}}
 (ROOT/'paper/results/reproducibility.json').write_text(json.dumps(manifest,indent=2))
