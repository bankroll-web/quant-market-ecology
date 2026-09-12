"""
CryptoHFT raw data reader.

Exact port of the canonical reader used by d06_replay_book.py and
exp01_replication_gate1_canonical.py. Behavior is frozen: do not change
signature detection, decompression, or the returned DataFrame.
"""
import io

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd


def read_cryptohft(path):
    """Read a CryptoHFT parquet file, transparently handling outer-zstd.

    - Plain parquet (magic b"PAR1") is read directly.
    - Outer-zstd parquet (magic b"\\x28\\xb5\\x2f\\xfd") is decompressed
      and the inner parquet payload is read.
    - Any other signature raises RuntimeError.
    """
    with open(path, "rb") as f:
        first4 = f.read(4)

    if first4 == b"PAR1":
        return pd.read_parquet(path)

    if first4 == b"\x28\xb5\x2f\xfd":
        with open(path, "rb") as f:
            compressed = f.read()

        dctx = zstd.ZstdDecompressor()

        with dctx.stream_reader(io.BytesIO(compressed)) as reader:
            raw = reader.read()

        if raw[:4] != b"PAR1":
            raise RuntimeError("Inner payload is not Parquet")

        return pq.read_table(pa.BufferReader(raw)).to_pandas()

    raise RuntimeError(f"Unknown file signature: {first4!r}")