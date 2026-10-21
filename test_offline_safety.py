"""Legacy manual probes must be inert when a regression runner imports them."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class OfflineSafetyTests(unittest.TestCase):
    def test_manual_probes_cannot_start_network_calls_on_import(self):
        root = Path(__file__).parent
        with patch('requests.post', side_effect=AssertionError('Network is forbidden during test import')), patch('requests.get', side_effect=AssertionError('Network is forbidden during test import')):
            for name in ('test_apify_run.py', 'test_google_scraper.py', 'test_indeed_scraper.py'):
                # These historical, credential-bearing probes are deliberately
                # untracked and absent in clean checkouts and deployments.
                if not (root / name).exists():
                    continue
                spec = importlib.util.spec_from_file_location('offline_probe', root / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)


if __name__ == '__main__':
    unittest.main()
