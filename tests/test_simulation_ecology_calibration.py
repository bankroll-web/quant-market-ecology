import tempfile
import unittest
from pathlib import Path
from src.simulation.ecology_calibration import read,fit,score,QUANTITIES
from src.simulation.book_change_rates import KINDS

class EcologyCalibrationTests(unittest.TestCase):
    def test_incomplete_rows_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.csv';p.write_text('exposure_seconds,bid_add_qty\n1,2\n1,')
            # A trailing blank field is also unusable, even when CSV parses it.
            with self.assertRaises((ValueError,TypeError)):read(p)

    def test_quantity_calibration_uses_training_exposure_and_does_not_refit(self):
        rows=[]
        for depth in range(1,10):
            r=dict(exposure_seconds=1.,pre_obi_top=0.,pre_bid_depth_10bps=depth,pre_ask_depth_10bps=depth)
            r.update({k:1 for k in KINDS});r.update({k:2 for k in QUANTITIES});rows.append(r)
        m=fit(rows);self.assertEqual(m['global_quantity_btc_per_second']['bid_add_qty'],2)
        before=m['depth_cutoffs_btc'][:]
        later=[{**rows[0],**{k:100 for k in QUANTITIES}}]
        result=score(later,m)
        self.assertEqual(result['quantity_rates']['bid_add_qty']['observed_btc_per_second'],100)
        self.assertEqual(result['quantity_rates']['bid_add_qty']['conditional_predicted_btc_per_second'],2)
        self.assertEqual(m['depth_cutoffs_btc'],before)
