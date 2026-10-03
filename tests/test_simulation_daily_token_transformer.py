import unittest
import numpy as np
import torch
from src.simulation.daily_token_transformer import TokenTransformer,tokenize,probabilities

class TransformerChecks(unittest.TestCase):
    def test_future_frame_cannot_change_past_hidden_states(self):
        torch.set_num_threads(2);torch.manual_seed(91);m=TokenTransformer().eval();x=torch.randint(0,720,(1,16,40));changed=x.clone();changed[:,8:]=torch.randint(0,720,(1,8,40))
        with torch.no_grad():a=m.hidden(x);b=m.hidden(changed)
        torch.testing.assert_close(a[:,:8],b[:,:8],atol=1e-6,rtol=1e-6)
    def test_tokenizer_ignores_future_values(self):
        tr=np.tile(np.linspace(-1,1,100)[:,None],(1,40));data=np.vstack([tr,np.full((1,40),1000)])
        t,b,m=tokenize(data,np.arange(101)<100)
        self.assertEqual(m['upper'],[1]*40)
        self.assertTrue(np.all(b[-1]==17));self.assertEqual(t.shape,(101,40))
    def test_probability_normalization_and_finite_gradients(self):
        p=probabilities(np.array([[1000,0,-1000],[1,2,3]]));np.testing.assert_allclose(p.sum(1),1)
        torch.manual_seed(91);m=TokenTransformer();x=torch.randint(0,720,(2,16,40));loss=torch.nn.functional.cross_entropy(m(x),torch.tensor([1,2]));loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertTrue(all(torch.isfinite(v.grad).all() for v in m.parameters() if v.grad is not None))

if __name__=='__main__':unittest.main()
