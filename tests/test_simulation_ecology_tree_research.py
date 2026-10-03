import unittest
import numpy as np
from src.simulation.ecology_tree_research import fit, actions, quote_targets

class EcologyTreeTests(unittest.TestCase):
    def test_planted_net_edge_and_range_guard(self):
        x=np.column_stack([np.linspace(-1,1,200)]*7)
        y=np.column_stack([np.where(x[:,0]>0,10,-10),np.where(x[:,0]>0,-10,10)])
        model=fit(x,y)
        side,_,_=actions(np.array([[-.5]*7,[.5]*7,[2]*7]),model)
        np.testing.assert_array_equal(side,[-1,1,0])
    def test_cost_and_quote_crossing(self):
        r={'observation':{'post_best_bid':99,'post_best_ask':101}}
        end={'post_best_bid':100,'post_best_ask':102}
        long,short=quote_targets(r,end)
        self.assertAlmostEqual(long,10000*(100/101-1)-6)
        self.assertAlmostEqual(short,10000*(99-102)/99-6)
        self.assertLess(long,0)
    def test_no_edge_keeps_wait(self):
        x=np.column_stack([np.linspace(-1,1,200)]*7)
        model=fit(x,np.full((200,2),-6.))
        side,_,_=actions(x,model)
        self.assertFalse(np.any(side))

if __name__=='__main__':unittest.main()
