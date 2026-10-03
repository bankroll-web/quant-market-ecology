import unittest
import numpy as np
import pandas as pd
import torch
from tokenizer_v1 import MarketTokenizer,SPEC
from train_real import Model,samples,L
class Checks(unittest.TestCase):
    def test_training_binner_unchanged_by_test_values(self):
        from tokenizer_v1 import MagBinner
        train=np.arange(1.,100);a=MagBinner(True).fit(train);old=a.edges.copy();a.transform(np.array([1e9]));np.testing.assert_array_equal(a.edges,old)
    def test_episode_and_index_gaps_excluded(self):
        n=50;df=pd.DataFrame({'episode_id':['a']*n,'mid_t1':np.arange(n)+100.,'t1_event_time_ms':np.arange(n),'interval_index':np.arange(n),'signed_flow_qty':np.ones(n),'total_flow_qty':np.ones(n)});tokens=pd.DataFrame(np.zeros((n,12),dtype=int));self.assertGreater(len(samples(df,tokens)[0]),0);df['episode_id']=[str(i) for i in range(n)]
        with self.assertRaises(ValueError):samples(df,tokens)
    def test_finite_multi_output_gradients(self):
        torch.set_num_threads(2);m=Model({f:3 for f in SPEC});fields,q,f,v=m(torch.zeros((2,L,12),dtype=torch.long));self.assertTrue(torch.all(q[:,1:]>=q[:,:-1]));(q.mean()+f.mean()+v.mean()+sum(a.mean() for a in fields)).backward();self.assertTrue(all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None))
if __name__=='__main__':unittest.main()
