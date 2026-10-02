import json
from pathlib import Path
import tempfile
import unittest
from src.simulation.capture_archive import CaptureArchive, verify_segment
from src.simulation.live_observer import Output


class ArchiveTests(unittest.TestCase):
    def test_rotation_restart_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            a = CaptureArchive(directory, max_bytes=1)
            a.append('book', {'x': 1}, 1)
            a.append('trade', {'x': 2}, 2)
            a.close()
            manifests = sorted(Path(directory).glob('*.manifest.json'))
            self.assertEqual(len(manifests), 2)
            self.assertEqual(sum(len(verify_segment(p)) for p in manifests), 2)
            b = CaptureArchive(directory)
            self.assertNotEqual(a.session, b.session)
            b.append('book', {}, 3)
            b.close()
            segment = manifests[0].parent / json.loads(manifests[0].read_text())['file']
            segment.write_bytes(segment.read_bytes().replace(b'book', b'BOOk'))
            with self.assertRaises(ValueError):
                verify_segment(manifests[0])

    def test_partial_not_promoted_and_write_failure_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            a = CaptureArchive(directory)
            a.append('book', {}, 1)
            self.assertEqual(list(Path(directory).glob('*.manifest.json')), [])
            a.handle.close()
            a.handle = None
            a.directory = Path(directory) / 'missing' / 'child'
            self.assertFalse(a.append('book', {}, 2))
            self.assertEqual(a.view()['status'], 'failed')
            a.close()
            self.assertEqual(list(Path(directory).glob('*.manifest.json')), [])

    def test_archive_cannot_be_served(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Output(directory, archive_directory=Path(directory) / 'raw')
