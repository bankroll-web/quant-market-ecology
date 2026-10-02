"""Private segmented raw recordings. Completed manifests verify bytes, not feed completeness."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import time
import uuid


class CaptureArchive:
    def __init__(self, directory, max_bytes=8 * 1024 * 1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session = uuid.uuid4().hex
        self.max_bytes = max_bytes
        self.index = 0
        self.handle = None
        self.error = None
        self.records = 0
        self.completed = 0
        self.last_received_ns = None
        self.bytes = 0

    def _open(self):
        if shutil.disk_usage(self.directory).free < 64 * 1024 * 1024:
            raise OSError("archive stopped: less than 64 MiB free; no recordings deleted")
        self.path = self.directory / f'{self.session}-{self.index:06d}.jsonl.partial'
        self.handle = self.path.open('xb')
        self.digest = hashlib.sha256()
        self.segment_records = 0
        self.segment_bytes = 0
        self.first_ns = None

    def append(self, kind, payload, received_ns):
        if self.error:
            return False
        try:
            data = (json.dumps(dict(kind=kind, received_ns=received_ns, payload=payload),
                               separators=(',', ':')) + '\n').encode()
            if self.handle and self.segment_bytes + len(data) > self.max_bytes:
                self._finish()
            if self.handle is None:
                self._open()
            written = self.handle.write(data)
            self.handle.flush()
            if written != len(data):
                raise OSError('short archive write')
            self.digest.update(data)
            self.segment_bytes += len(data)
            self.segment_records += 1
            self.records += 1
            self.bytes += len(data)
            self.first_ns = received_ns if self.first_ns is None else self.first_ns
            self.last_received_ns = received_ns
            return True
        except OSError as error:
            self.error = str(error)
            return False

    def _finish(self):
        if self.handle is None:
            return
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()
        self.handle = None
        target = self.path.with_suffix('')
        self.path.replace(target)
        manifest = dict(schema=1, session=self.session, segment=self.index,
                        file=target.name, sha256=self.digest.hexdigest(),
                        records=self.segment_records, bytes=self.segment_bytes,
                        first_received_ns=self.first_ns, last_received_ns=self.last_received_ns,
                        closed_ns=time.time_ns(), feed_completeness='not established')
        temp = target.with_suffix('.manifest.tmp')
        with temp.open('x') as handle:
            json.dump(manifest, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(target.with_suffix('.manifest.json'))
        self.completed += 1
        self.index += 1

    def close(self):
        if not self.error:
            try:
                self._finish()
            except OSError as error:
                self.error = str(error)
        if self.handle:
            self.handle.close()
            self.handle = None

    def view(self):
        return dict(status='failed' if self.error else 'recording', session=self.session,
                    records=self.records, bytes=self.bytes, completed_segments=self.completed,
                    last_received_ns=self.last_received_ns,
                    persistence='requires a persistent mounted volume; otherwise ephemeral',
                    integrity='completed segments carry SHA-256 manifests; unfinished segments excluded',
                    error=self.error)


def verify_segment(manifest_path):
    """Reject partial files, missing pairs, corruption and changed record counts."""
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    name = manifest['file']
    if Path(name).name != name or not name.endswith('.jsonl'):
        raise ValueError('invalid segment filename')
    data = (path.parent / name).read_bytes()
    if not data.endswith(b'\n') or len(data) != manifest['bytes']:
        raise ValueError('incomplete segment')
    if hashlib.sha256(data).hexdigest() != manifest['sha256']:
        raise ValueError('segment hash mismatch')
    rows = [json.loads(row) for row in data.splitlines()]
    if len(rows) != manifest['records']:
        raise ValueError('record count mismatch')
    return rows
