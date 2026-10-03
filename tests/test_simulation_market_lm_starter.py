import unittest
import numpy as np
import torch
from src.simulation.market_lm_starter import make_synthetic,build_dataset,masked_mean,conformal_widen,MarketLM,compute_loss,get_batch
class Checks(unittest.TestCase):
    def test_future_mutation_does_not_change_training_scalers(self):
        r=make_synthetic(1000);a=build_dataset(r,600);changed={k:v.copy() for k,v in r.items()};changed['mid'][600:]*=10;changed['size'][600:]*=100
        b=build_dataset(changed,600);self.assertEqual(a['scaler'],b['scaler']);torch.testing.assert_close(a['tokens'][:600],b['tokens'][:600]);torch.testing.assert_close(a['R'][:400],b['R'][:400])
    def test_broadcast_mean(self):self.assertEqual(masked_mean(torch.ones(2,3,5),torch.ones(2,3,1)).item(),1)
    def test_conformal_order_statistic(self):
        self.assertEqual(conformal_widen(torch.zeros(4),torch.zeros(4),torch.arange(1.,5.),.6),3)
    def test_smoke_finite_loss_and_causal_output(self):
        torch.set_num_threads(2);torch.manual_seed(1);d=build_dataset(make_synthetic(1000),600);m=MarketLM(d=32,layers=1,heads=4,max_len=16);b=get_batch(d,[0,20],16);loss,_=compute_loss(m,b);loss.backward();self.assertTrue(torch.isfinite(loss));m.eval();x=b['x'];z=x.clone();z[:,8:]=0
        with torch.no_grad():torch.testing.assert_close(m(x)['q'][:,:8],m(z)['q'][:,:8])
if __name__=='__main__':unittest.main()
