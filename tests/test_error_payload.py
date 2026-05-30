from __future__ import annotations

import unittest

from src.errors import ApiError


class ErrorPayloadTests(unittest.TestCase):
    def test_api_error_payload_shape(self) -> None:
        err = ApiError(
            code="BREADTH_FETCH_SSL_EOF",
            message="拉取失败",
            hint="请检查代理",
            retryable=True,
            detail="ssl eof",
            status_code=502,
        )
        payload = err.to_payload()
        self.assertEqual(payload["code"], "BREADTH_FETCH_SSL_EOF")
        self.assertEqual(payload["message"], "拉取失败")
        self.assertEqual(payload["hint"], "请检查代理")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["detail"], "ssl eof")


if __name__ == "__main__":
    unittest.main()
