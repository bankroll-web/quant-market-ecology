import unittest
import json
import tempfile
from pathlib import Path

import numpy as np

from src.simulation.clustered_flow import hawkes
from src.simulation.learning_book import FIFOBook
from src.simulation.learning_market_maker import ACTIONS, CAP, Environment, greedy, load_policy, tape


class LearningBookTest(unittest.TestCase):
    def test_fifo_partial_fills_and_reposting_loses_priority(self):
        book = FIFOBook()
        book.post('first', 'ask', 101, 3)
        book.post('second', 'ask', 101, 4)
        book.execute('buyer', 'buy', 2)
        self.assertEqual(book.inventory['first'], -2)
        self.assertEqual(book.inventory['second'], 0)
        book.cancel('first')
        book.post('first', 'ask', 101, 3)
        book.execute('buyer', 'buy', 5)
        self.assertEqual(book.inventory['second'], -4)
        self.assertEqual(book.inventory['first'], -3)
        self.assertEqual(book.resting('first', 'ask'), 2)

    def test_price_priority_direction_and_volume_conservation(self):
        book = FIFOBook()
        book.post('maker', 'bid', 99, 5)
        book.post('far', 'ask', 103, 4)
        book.post('near', 'ask', 101, 2)
        before_bid = book.best('bid')
        fill = book.execute('buyer', 'buy', 3)
        self.assertEqual(fill['filled_lots'], 3)
        self.assertEqual(book.inventory['near'], -2)
        self.assertEqual(book.inventory['far'], -1)
        self.assertEqual(book.best('ask'), 103)
        self.assertEqual(book.best('bid'), before_bid)
        self.assertEqual(sum(book.inventory.values()), 0)
        self.assertAlmostEqual(sum(book.cash.values()), 0)
        self.assertEqual(book.execute('buyer', 'buy', 20)['unfilled_lots'], 17)

    def test_post_only_self_trade_and_fees(self):
        book = FIFOBook(maker_fee_bps=1, taker_fee_bps=2)
        book.post('maker', 'ask', 1000, 1)
        with self.assertRaises(ValueError):
            book.post('other', 'bid', 1000, 1)
        book.execute('buyer', 'buy', 1)
        self.assertAlmostEqual(sum(book.cash.values()), -0.0003)
        book.post('buyer', 'ask', 1000, 1)
        fill = book.execute('buyer', 'buy', 1)
        self.assertEqual(fill['filled_lots'], 0)
        self.assertEqual(book.inventory['buyer'], 1)

    def test_hawkes_rejects_explosive_kernel_and_has_ordered_events(self):
        with self.assertRaises(ValueError):
            hawkes(1, 10, self_jump=1.5, cross_jump=0.1, decay=1)
        events = hawkes(1, 10)
        self.assertEqual(events, sorted(events))
        self.assertTrue(all(0 <= t < 10 and 1 <= q <= 5 for t, side, q in events))

    def test_inventory_capacity_and_cash_based_terminal_reward(self):
        for action in range(9):
            events = tape(3, 'burst')[:12]
            env = Environment(events)
            while env.index < len(events):
                env.step(action)
                q = env.book.inventory['learner']
                self.assertLessEqual(abs(q), CAP)
                self.assertLessEqual(q + env.book.resting('learner', 'bid'), CAP)
                self.assertLessEqual(env.book.resting('learner', 'ask') - q, CAP)
            self.assertEqual(env.book.inventory['learner'], 0)
            self.assertAlmostEqual(env.total_reward, env.book.cash['learner'] - env.risk_cost)

    def test_pause_has_no_exposure_or_reward_and_unvisited_state_is_conservative(self):
        env = Environment(tape(5)[:8])
        while env.index < len(env.events):
            env.step(7)
        self.assertEqual(env.total_reward, 0)
        self.assertEqual(env.book.filled['learner'], 0)
        self.assertEqual(greedy(np.zeros(9)), 7)

    def test_exported_policy_can_be_loaded_and_rejects_wrong_action_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            model = dict(environment_version=1, actions=list(ACTIONS),
                         values=np.zeros((5, 3, 3, 2, 9)).tolist(),
                         visits=np.zeros((5, 3, 3, 2, 9), dtype=int).tolist())
            path.write_text(json.dumps(model))
            _, values, visits = load_policy(path)
            self.assertEqual(greedy(values[0, 0, 0, 0]), 7)
            model['actions'].reverse()
            path.write_text(json.dumps(model))
            with self.assertRaises(ValueError):
                load_policy(path)


if __name__ == '__main__':
    unittest.main()
