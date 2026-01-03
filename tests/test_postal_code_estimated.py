import os
import unittest
from unittest.mock import Mock, patch


from TutorDexAggregator.extractors import postal_code_estimated as mod


class TestPostalCodeEstimated(unittest.TestCase):
    def setUp(self) -> None:
        self._old_disable = os.environ.get("DISABLE_NOMINATIM")
        os.environ["DISABLE_NOMINATIM"] = "0"
        mod._estimate_postal_from_cleaned_address.cache_clear()

    def tearDown(self) -> None:
        if self._old_disable is None:
            os.environ.pop("DISABLE_NOMINATIM", None)
        else:
            os.environ["DISABLE_NOMINATIM"] = self._old_disable
        mod._estimate_postal_from_cleaned_address.cache_clear()

    def test_skips_when_postal_code_present(self):
        with patch.object(mod.requests, "get") as get:
            res = mod.estimate_postal_codes(
                parsed={"postal_code": ["642196"], "address": ["196B Boon Lay Drive"]},
                raw_text="Address: 196B Boon Lay Drive (S)642196",
            )
            self.assertIsNone(res.estimated)
            self.assertEqual(res.meta.get("skipped"), "postal_code_present")
            get.assert_not_called()

    def test_estimates_from_address(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = [{"address": {"postcode": "642196"}}]

        with patch.object(mod.requests, "get", return_value=mock_resp) as get:
            res = mod.estimate_postal_codes(
                parsed={"postal_code": None, "address": ["196B Boon Lay Drive"]},
                raw_text="Code ID: 0101pn\nAddress: 196B Boon Lay Drive\n",
            )
            self.assertEqual(res.estimated, ["642196"])
            self.assertTrue(res.meta.get("ok"))
            self.assertGreaterEqual(get.call_count, 1)

    def test_estimates_from_raw_text_address_hint(self):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.json.return_value = [{"display_name": "196B Boon Lay Drive, Singapore 642196"}]

        with patch.object(mod.requests, "get", return_value=mock_resp):
            res = mod.estimate_postal_codes(
                parsed={"postal_code": None, "address": None},
                raw_text="Address: 196B Boon Lay Drive\nRate: $40/hr\n",
            )
            self.assertEqual(res.estimated, ["642196"])


if __name__ == "__main__":
    unittest.main()

