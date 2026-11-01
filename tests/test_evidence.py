import unittest
from go2_ppo.evidence import verify_time_grid


class TimeGridTests(unittest.TestCase):
    def test_missing_duplicate_nonfinite_and_shifted_samples_are_rejected(self):
        self.assertEqual(verify_time_grid([0., .01, .02], .01, .02), 3)
        for times in ([0., .02], [0., .01, .01], [.01, .02], [0., float('nan')]):
            with self.assertRaises(ValueError):
                verify_time_grid(times, .01, .02)
