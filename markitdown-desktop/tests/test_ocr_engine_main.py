import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ocr_engine_main", ROOT / "ocr-engine" / "main.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _FakeOcr:
    def predict(self, _image):
        return [{"res": {"rec_texts": ["离线"]}}]


class OcrEngineMainTests(unittest.TestCase):
    def test_jsonl_loop_reuses_model_and_keeps_request_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.jpg"
            image.write_bytes(b"not decoded by fake OCR")
            stream = io.StringIO(
                json.dumps(
                    {
                        "version": 1,
                        "request_id": "one",
                        "input_path": str(image),
                        "file_type": "image",
                        "pages": [],
                        "language": "chinese_english",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "version": 1,
                        "request_id": "two",
                        "input_path": str(image),
                        "file_type": "image",
                        "pages": [],
                        "language": "chinese_english",
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + '{"version":1,"request_id":"bad"}\n'
            )
            output = io.StringIO()
            with patch.object(MODULE, "create_ocr", return_value=_FakeOcr()) as factory:
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, MODULE.run_jsonl(stream))

            events = [json.loads(line) for line in output.getvalue().splitlines()]
            results = [event for event in events if event.get("type") == "result"]
            errors = [event for event in events if event.get("type") == "error"]
            self.assertEqual(["one", "two"], [event["request_id"] for event in results])
            self.assertEqual("bad", errors[0]["request_id"])
            self.assertEqual("INVALID_REQUEST", errors[0]["code"])
            factory.assert_called_once()


if __name__ == "__main__":
    unittest.main()
