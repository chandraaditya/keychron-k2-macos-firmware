import unittest
from unittest.mock import patch
import battery_logger as logger


class LoggerTests(unittest.TestCase):
    def test_denied_read_is_missing_not_zero(self):
        with patch.object(logger, 'read_json', return_value=(None, 'access_denied')):
            row = logger.collect(0)
        self.assertIsNone(row['battery_percent'])
        self.assertIsNone(row['standard_report_percent'])
        self.assertEqual(row['status'], 'error')

    def test_standard_zero_is_retained_next_to_internal_estimate(self):
        with patch.object(logger, 'read_json', side_effect=[
            ({'battery_percent': 53, 'cached_report_percent': 0, 'sensor_average_raw': 1733}, None),
            ({'raw_battery_percent': 0}, None),
        ]):
            row = logger.collect(0)
        self.assertEqual(row['battery_percent'], 53)
        self.assertEqual(row['standard_report_percent'], 0)
        self.assertEqual(row['status'], 'ok')

    def test_summary_uses_valid_samples_and_reports_gaps(self):
        rows = [{'battery_percent': 53, 'standard_report_percent': 0, 'elapsed_seconds': 0},
                {'battery_percent': None, 'standard_report_percent': None, 'elapsed_seconds': 300},
                {'battery_percent': 49, 'standard_report_percent': 0, 'elapsed_seconds': 900}]
        summary = logger.summarize(rows, {'duration_seconds': 3600, 'settings': {}}, True, 'stopped')
        self.assertEqual(summary['change_percentage_points'], -4)
        self.assertEqual(summary['max_gap_seconds'], 900)
        self.assertEqual(summary['valid_internal_samples'], 2)


if __name__ == '__main__':
    unittest.main()
