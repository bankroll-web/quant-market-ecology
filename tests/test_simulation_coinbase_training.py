import tempfile,unittest,json
from pathlib import Path
from src.simulation.capture_archive import CaptureArchive
from src.simulation.coinbase_training import dataset,train
class CoinbaseTrainingTests(unittest.TestCase):
    def test_verified_captures_and_engineering_floor(self):
        with tempfile.TemporaryDirectory() as d:
            archive=CaptureArchive(d)
            for i in range(25):
                t=i*100000000
                archive.append('coinbase_model_observation',dict(provider='Coinbase Exchange',symbol='BTC-USD',available_ns=t,event_ns=t,features=[0,0,1,1,0],source_update_id=i,midpoint=100+i*.01),t)
            archive.close();paths=list(Path(d).glob('*.manifest.json'))
            rows=dataset(paths);self.assertEqual(len(rows),2)
            report=train(paths,Path(d)/'out.json');self.assertEqual(report['status'],'insufficient_data');self.assertFalse(report['qualified'])
