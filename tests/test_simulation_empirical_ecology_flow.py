import unittest,json
from pathlib import Path
from src.simulation.empirical_ecology_flow import sample,simulate_prefix
from src.simulation.ecology import common_flow,run
class EmpiricalFlowTests(unittest.TestCase):
    def test_gap_and_sizes(self):
        pool=[dict(start_ns=i*2,end_ns=i*2+1,episode=1,duration_seconds=1.,trades=[('buy',i+.5),('sell',.1)]) for i in range(3)]
        flow,source=sample(pool,7,30)
        self.assertEqual((flow,source),sample(pool,7,30));self.assertEqual(len(set(p['block'] for p in source)),30)
        for trades,p in zip(flow,source):self.assertEqual(trades,pool[p['training_window']]['trades'])
    def test_prefix_parity(self):
        params=json.loads(Path('configs/simulation_v1_demo.json').read_text())['calibration_from_valid_samples']
        flow=common_flow(params,7);original,_=run(params,flow,False)
        for row,old in zip(simulate_prefix(params,flow[:120]),original[1:121]):
            for key in ('mid','bid','ask'):self.assertEqual(row[key],old[key])
    def test_invalid(self):
        with self.assertRaises(ValueError):sample([],7)
