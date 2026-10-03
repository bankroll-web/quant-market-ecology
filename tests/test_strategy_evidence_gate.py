import unittest
from strategy_evidence_gate import screen
class GateTests(unittest.TestCase):
 def base(self):return dict(validation_trades=50,validation_active_days=10,validation_bps_day=2,validation_daily_bootstrap_95_ci=[.2,4])
 def test_lucky_trade_rejected(self):
  c=self.base();c['validation_trades']=1
  self.assertIn('too_few_validation_trades',screen(c,dict(log_loss=.6,baseline_log_loss=.7))['reasons'])
 def test_baseline_failure_rejected(self):
  self.assertIn('forecast_does_not_beat_constant_baseline',screen(self.base(),dict(log_loss=.8,baseline_log_loss=.7))['reasons'])
 def test_missing_uncertainty_rejected(self):
  c=self.base();del c['validation_daily_bootstrap_95_ci']
  self.assertFalse(screen(c,dict(log_loss=.6,baseline_log_loss=.7))['passed_screen'])
 def test_pass_is_not_order_permission(self):
  r=screen(self.base(),dict(log_loss=.6,baseline_log_loss=.7));self.assertTrue(r['passed_screen']);self.assertFalse(r['qualified']);self.assertFalse(r['orders_enabled'])
if __name__=='__main__':unittest.main()
