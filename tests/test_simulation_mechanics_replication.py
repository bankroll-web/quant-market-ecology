import csv
from pathlib import Path
import tempfile
import unittest
import pyarrow as pa
import pyarrow.parquet as pq
from src.simulation.book_changes import COLS
from src.simulation.csv_book_to_parquet import convert
from src.simulation.ecology_mechanics_replication import load_frozen


class ReplicationTests(unittest.TestCase):
    def fixture(self,path,last='10632991592699.0'):
        row=dict(received_time='1779786003693000001',event_time='1779786003693',transaction_time='1779786003687',event_type='snapshot',
                 first_update_id='',final_update_id='10632991592699',prev_final_update_id='',last_update_id=last,side='ask',price='76695.40',quantity='10.748')
        with path.open('w') as handle:
            w=csv.DictWriter(handle,fieldnames=COLS);w.writeheader();w.writerow(row)
    def test_csv_preserves_nanoseconds_and_decimal_identifier(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'book.csv';target=Path(d)/'book.parquet';self.fixture(source)
            result=convert(source,target);data=pq.read_table(target).to_pydict()
            self.assertEqual(data['received_time'],[1779786003693000001])
            self.assertEqual(data['last_update_id'],[10632991592699]);self.assertEqual(data['first_update_id'],[None]);self.assertEqual(result['rows'],1)
    def test_fractional_identifier_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'book.csv';self.fixture(source,'10632991592699.5')
            with self.assertRaises(pa.ArrowInvalid):convert(source,Path(d)/'book.parquet')
    def test_frozen_baseline_changes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'baseline.json';p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Frozen baseline changed'):load_frozen(p)
    def test_saved_baseline_is_accepted_without_refitting(self):
        path=Path(__file__).resolve().parents[1]/'docs/price_mechanics/summary.json'
        baseline=load_frozen(path)
        self.assertEqual(baseline['training_hour'],'2026-05-25_00')
        self.assertEqual(set(baseline['models']),{'trade_only','book_only','joint'})
