import unittest
import numpy as np
from src.simulation.robust_ecology_response import average_depth,feature,fit,prediction


class RobustResponseTests(unittest.TestCase):
    def test_depth_integral_uses_duration_and_excludes_endpoint_state(self):
        book=[dict(received_time_ns=t,episode=1,post_bid_top_qty=q,post_ask_top_qty=q) for t,q in [(0,2),(250000000,6),(1000000000,1000)]]
        self.assertEqual(average_depth(book,0,1000000000,1),5)
        book[1]['episode']=2
        with self.assertRaises(ValueError):average_depth(book,0,1000000000,1)
    def test_clipping_and_soft_transform_have_distinct_behavior(self):
        rows=[dict(ofi_pressure=x) for x in (-100,0,100)]
        transform=dict(clip_low=-2,clip_high=3,asinh_scale=2)
        np.testing.assert_array_equal(feature(rows,'training_quantile_clip',transform),[-2,0,3])
        values=feature(rows,'asinh_pressure',transform)
        self.assertAlmostEqual(values[0],-values[2]);self.assertEqual(values[1],0)
    def test_evaluation_does_not_mutate_training_fit(self):
        train=[dict(ofi_pressure=float(x),move_bps=float(x)) for x in (-2,-1,0,1,2)]
        transform=dict(clip_low=-2,clip_high=2,asinh_scale=1)
        model=fit(train,'training_quantile_clip',transform);before=model.copy()
        p=prediction([dict(ofi_pressure=1000000.)],'training_quantile_clip',transform,model)
        self.assertEqual(model,before);self.assertLess(abs(p[0]),3)
