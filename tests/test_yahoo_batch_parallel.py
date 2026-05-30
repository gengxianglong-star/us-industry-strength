from __future__ import annotations

import unittest

from src.stock_rs import _yahoo_rs_batches


class YahooBatchParallelTests(unittest.TestCase):
    def test_yahoo_rs_batches_splits_evenly(self) -> None:
        batches = _yahoo_rs_batches(["A", "B", "C", "D", "E"], batch_size=2)
        self.assertEqual(batches, [["A", "B"], ["C", "D"], ["E"]])

    def test_yahoo_rs_batches_empty(self) -> None:
        self.assertEqual(_yahoo_rs_batches([], batch_size=20), [])


if __name__ == "__main__":
    unittest.main()
