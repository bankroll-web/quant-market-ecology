import unittest
from decimal import Decimal as D
from src.simulation.live_ecology import walk, experiment, black_scholes, LiveEcology
from src.simulation.live_observer import DepthObserver

class LiveEcologyTests(unittest.TestCase):
    def setUp(self):
        self.bids={D('100'):D('2'),D('99'):D('5')}
        self.asks={D('101'):D('2'),D('102'):D('5')}

    def test_walk_conservation_vwap_and_source_unchanged(self):
        result=walk(self.bids,self.asks,3)
        self.assertEqual(result['filled_btc'],3)
        self.assertAlmostEqual(result['vwap'],304/3)
        self.assertEqual(self.asks[D('101')],2)
        self.assertEqual(sum(result['asks'].values()),4)
        self.assertEqual(result['midpoint'],101)
        sell=walk(self.bids,self.asks,-3)
        self.assertLess(sell['midpoint'],100.5)

    def test_exhaustion_is_unknown_and_thinning_increases_impact(self):
        full=experiment(self.bids,self.asks,1.5)
        thin=experiment(self.bids,self.asks,1.5,.5)
        self.assertGreater(thin['move_bps'],full['move_bps'])
        empty=experiment(self.bids,self.asks,20)
        self.assertEqual(empty['initiating_unfilled_btc'],13)
        self.assertIsNone(empty['move_bps'])

    def test_signed_gamma_hedge_direction_and_partial_hedge(self):
        long=experiment(self.bids,self.asks,3,gamma=.5)
        short=experiment(self.bids,self.asks,3,gamma=-.5)
        self.assertLess(long['hedge_signed_btc'],0)
        self.assertGreater(short['hedge_signed_btc'],0)
        self.assertLessEqual(long['move_bps'],short['move_bps'])
        big=experiment(self.bids,self.asks,3,gamma=-100)
        self.assertGreater(big['hedge_unfilled_btc'],0)
        self.assertTrue(big['book_exhausted'])

    def test_bs_put_call_parity_gamma_and_validation(self):
        import math
        price=black_scholes(100,105,.5,.4,.03)
        self.assertAlmostEqual(price['call']-price['put'],100-105*math.exp(-.03*.5))
        self.assertGreater(price['gamma'],0)
        self.assertAlmostEqual(price['call_delta']-price['put_delta'],1)
        with self.assertRaises(ValueError):black_scholes(100,100,0,.4)

    def test_stale_clears_scenarios_and_volatility_window(self):
        o=DepthObserver();o.snapshot(dict(lastUpdateId=1,bids=[['100','2'],['99','5']],asks=[['101','2'],['102','5']]))
        e=LiveEcology()
        for t in range(61):
            now=(t+1)*1_000_000_000
            o.update(dict(e='depthUpdate',s='BTCUSDT',U=t+1,u=t+2,pu=t+1,E=(t+1)*1000,b=[],a=[]),now)
            result=e.update(o,now)
        self.assertEqual(result['monte_carlo']['status'],'illustrative')
        self.assertEqual(result['monte_carlo']['p05'],100.5)
        paused=e.update(o,now+300_000_000)
        self.assertEqual(paused['scenarios'],[])
        self.assertEqual(len(e.samples),0)
        o.invalidate('sequence_gap')
        self.assertEqual(e.update(o,now)['status'],'paused')

    def test_rollout_reproducibility_conservation_and_inventory_caps(self):
        from src.simulation.live_rollout import rollout
        result=rollout(self.bids,self.asks)
        self.assertEqual(result,rollout(self.bids,self.asks))
        self.assertEqual(result['inventory_sum_btc'],0)
        self.assertAlmostEqual(sum(p['cash_quote'] for p in result['participants']),-result['total_paid_fees_quote'])
        self.assertAlmostEqual(sum(p['marked_wealth_quote'] for p in result['participants']),-result['total_paid_fees_quote'])
        for row in result['trace']:
            self.assertLessEqual(abs(row['maker_A_inventory_btc']),.2+1e-10)
            self.assertLessEqual(abs(row['maker_B_inventory_btc']),.2+1e-10)
        self.assertEqual(self.asks[D('101')],2)
        gamma=rollout(self.bids,self.asks,signed_gamma=-100)
        dealer=next(p for p in gamma['participants'] if p['role']=='assumed_gamma_dealer')
        self.assertLessEqual(abs(dealer['inventory_btc']),.5+1e-10)

    def test_simulation_advances_without_showing_future_and_reanchors(self):
        o=DepthObserver();o.snapshot(dict(lastUpdateId=1,bids=[['100','2'],['99','5']],asks=[['101','2'],['102','5']]))
        e=LiveEcology()
        for t in range(31):
            now=(t+1)*1_000_000_000
            o.update(dict(e='depthUpdate',s='BTCUSDT',U=t+1,u=t+2,pu=t+1,E=(t+1)*1000,b=[],a=[]),now)
            r=e.update(o,now)['rollouts']
            self.assertEqual(r['simulation_second'],t%30)
            self.assertEqual(len(r['baseline']['trace']),t%30+1)
            self.assertEqual(r['baseline']['participants'],r['baseline']['trace'][-1]['participants'])
            self.assertEqual(r['generated_ns'],(1 if t<30 else 31)*1_000_000_000)
