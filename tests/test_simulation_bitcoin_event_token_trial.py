import unittest
import torch
from src.simulation.bitcoin_event_token_trial import BookTokenModel
class ModelChecks(unittest.TestCase):
    def test_ordered_quantiles_and_finite_gradients(self):
        torch.set_num_threads(2);torch.manual_seed(91);m=BookTokenModel(129);x=torch.randint(0,129,(2,8,6));q,v=m(x);self.assertTrue(torch.all(q[:,1:]>=q[:,:-1]));(q.mean()+v.mean()).backward();self.assertTrue(all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None))
if __name__=='__main__':unittest.main()
