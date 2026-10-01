"""Paper-inspired bounded tabular RL sandbox. Synthetic training, not BTC fitting."""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import numpy as np

from .clustered_flow import hawkes
from .learning_book import FIFOBook

OWNER = 'learner'
ACTIONS = ('tight', 'tight_inventory_skew', 'medium', 'medium_inventory_skew',
           'wide', 'wide_inventory_skew', 'keep', 'pause', 'hedge')
WIDTHS = (1, 2, 4)
CAP = 20
SECONDS = 120
PENALTY = 0.0002  # USDT / squared inventory lot / second; assumed objective.
TRAIN_SEEDS = tuple(range(200))
TEST_SEEDS = tuple(range(10000, 10030))


def tape(seed, scenario='base'):
    rng = random.Random(seed + 991)
    groups = [[] for _ in range(SECONDS)]
    events = hawkes(seed, SECONDS, base_rate=2.4 if scenario == 'burst' else 1.2,
                    self_jump=0.8 if scenario == 'burst' else 0.5)
    for timestamp, side, lots in events:
        groups[int(timestamp)].append((side, lots))
    reference = 770000
    out = []
    for second, orders in enumerate(groups):
        net = sum(q if side == 'buy' else -q for side, q in orders)
        # Exogenous quote-anchor update, not a fitted/endogenous Hawkes LOB.
        move = (1 if net > 0 else -1 if net < 0 else 0) + rng.choice((-1, 0, 1))
        if scenario == 'jump' and second == SECONDS // 2:
            move += 100
        out.append(dict(second=second, reference=reference, next_reference=reference + move,
                        orders=orders, withdrawal=scenario == 'withdrawal' and 45 <= second < 75))
        reference += move
    return out


class Environment:
    def __init__(self, events, maker_fee_bps=0., taker_fee_bps=0.5):
        self.events = events
        self.book = FIFOBook(maker_fee_bps=maker_fee_bps, taker_fee_bps=taker_fee_bps)
        self.index, self.last_flow = 0, 0
        self.reference = events[0]['reference']
        self.max_inventory, self.risk_cost, self.total_reward = 0, 0., 0.
        self.trace = []
        self.refresh_rival(False)

    def refresh_rival(self, withdrawal, terminal=False):
        self.book.cancel('rival')
        distances = (8, 16, 32, 64) if withdrawal else (2, 4, 8, 16)
        for side in ('bid', 'ask'):
            for distance in distances:
                price = self.reference + (distance if side == 'ask' else -distance)
                opposite = self.book.best('bid' if side == 'ask' else 'ask')
                if opposite is not None:
                    price = max(price, opposite + 1) if side == 'ask' else min(price, opposite - 1)
                self.book.post('rival', side, price, 50 if terminal else 3)

    def state(self):
        q = self.book.inventory[OWNER]
        inventory_band = max(-2, min(2, q // 5))
        flow_band = 1 if self.last_flow > 3 else -1 if self.last_flow < -3 else 0
        time_band = min(2, 3 * self.index // len(self.events))
        bid, ask = self.book.best('bid'), self.book.best('ask')
        spread_band = 1 if bid is None or ask is None or ask - bid > 8 else 0
        return (inventory_band + 2, flow_band + 1, time_band, spread_band)

    def quote(self, action):
        if action == 6:  # Preserve surviving queue positions.
            return
        self.book.cancel(OWNER)
        if action == 7:
            return
        q = self.book.inventory[OWNER]
        if action == 8:
            if q:
                self.book.execute(OWNER, 'sell' if q > 0 else 'buy', min(abs(q), 4))
            return
        width = WIDTHS[action // 2]
        skew = (-1 if q > 0 else 1 if q < 0 else 0) if action % 2 else 0
        for side in ('bid', 'ask'):
            capacity = CAP - q if side == 'bid' else CAP + q
            for level in range(2):
                if capacity <= 0:
                    break
                lots = min(2, capacity)
                price = self.reference + skew + ((width + 2 * level) if side == 'ask' else -(width + 2 * level))
                opposite = self.book.best('bid' if side == 'ask' else 'ask')
                if opposite is not None:
                    price = max(price, opposite + 1) if side == 'ask' else min(price, opposite - 1)
                self.book.post(OWNER, side, price, lots)
                capacity -= lots

    def step(self, action):
        if self.index >= len(self.events) or type(action) is not int or not 0 <= action < len(ACTIONS):
            raise ValueError('Invalid action or completed episode')
        event = self.events[self.index]
        before = self.book.wealth(OWNER, self.reference)
        self.refresh_rival(event['withdrawal'])
        self.quote(action)
        for side, lots in event['orders']:
            self.book.execute('taker', side, lots)
            self.book.check()
            if abs(self.book.inventory[OWNER]) > CAP:
                raise AssertionError('Inventory limit breached')
            self.max_inventory = max(self.max_inventory, abs(self.book.inventory[OWNER]))
        self.last_flow = sum(q if s == 'buy' else -q for s, q in event['orders'])
        self.reference = event['next_reference']
        q = self.book.inventory[OWNER]
        risk = PENALTY * q * q
        self.risk_cost += risk
        self.index += 1
        done = self.index == len(self.events)
        if done:
            # Liquidate through FIFO book, paying taker costs, rather than mark-only profit.
            self.book.cancel(OWNER)
            self.refresh_rival(False, terminal=True)
            if q:
                result = self.book.execute(OWNER, 'sell' if q > 0 else 'buy', abs(q))
                if result['unfilled_lots']:
                    raise AssertionError('Terminal inventory not liquidated')
        wealth = self.book.wealth(OWNER, self.reference)
        reward = wealth - before - risk
        self.total_reward += reward
        self.trace.append(dict(second=event['second'], action=ACTIONS[action],
            reference_usdt=self.reference * self.book.tick, inventory_lots=self.book.inventory[OWNER],
            cash_usdt=self.book.cash[OWNER], wealth_usdt=wealth, reward_usdt=reward))
        return self.state(), reward, done

    def result(self):
        return dict(terminal_cash_usdt=self.book.cash[OWNER], risk_adjusted_reward_usdt=self.total_reward,
                    inventory_penalty_usdt=self.risk_cost, max_abs_inventory_lots=self.max_inventory,
                    terminal_inventory_lots=self.book.inventory[OWNER], executed_lots=self.book.filled[OWNER])


def greedy(values):
    # Deterministic conservative tie rule; unvisited states choose pause.
    return 7 if np.all(values == values[0]) else int(np.argmax(values))


def load_policy(path):
    model = json.loads(Path(path).read_text())
    values = np.asarray(model['values'], dtype=float)
    visits = np.asarray(model['visits'], dtype=int)
    if (model['actions'] != list(ACTIONS) or values.shape != (5, 3, 3, 2, len(ACTIONS)) or
            visits.shape != values.shape or not np.isfinite(values).all() or (visits < 0).any() or
            model.get('environment_version') != 1):
        raise ValueError('Policy incompatible with this environment')
    return model, values, visits


def train():
    values = np.zeros((5, 3, 3, 2, len(ACTIONS)))
    visits = np.zeros_like(values, dtype=int)
    rng = random.Random(71)
    rewards = []
    for episode, seed in enumerate(TRAIN_SEEDS):
        env = Environment(tape(seed))
        state = env.state()
        epsilon = max(0.1, 0.8 * (1 - episode / len(TRAIN_SEEDS)))
        while True:
            action = rng.randrange(len(ACTIONS)) if rng.random() < epsilon else greedy(values[state])
            following, reward, done = env.step(action)
            visits[state + (action,)] += 1
            rate = 0.2
            # Finite-horizon undiscounted reward; terminal value is zero.
            target = reward + (0 if done else float(np.max(values[following])))
            values[state + (action,)] += rate * (target - values[state + (action,)])
            state = following
            if done:
                break
        rewards.append(env.total_reward)
    return values, visits, rewards


def evaluate(values):
    summaries, traces = {}, []
    for scenario in ('base', 'burst', 'withdrawal', 'jump', 'fees_1bps'):
        scenario_results = {}
        for policy in ('learned', 'fixed_medium', 'inventory_skew', 'no_quotes'):
            rows = []
            for seed in TEST_SEEDS:
                events = tape(seed, scenario if scenario != 'fees_1bps' else 'base')
                env = Environment(events, maker_fee_bps=1 if scenario == 'fees_1bps' else 0)
                while env.index < len(events):
                    action = greedy(values[env.state()]) if policy == 'learned' else {
                        'fixed_medium': 2, 'inventory_skew': 3, 'no_quotes': 7}[policy]
                    env.step(action)
                rows.append(dict(seed=seed, **env.result()))
                if seed == TEST_SEEDS[0]:
                    traces.extend(dict(scenario=scenario, policy=policy, **r) for r in env.trace)
            scenario_results[policy] = dict(episodes=len(rows),
                mean_terminal_cash_usdt=float(np.mean([r['terminal_cash_usdt'] for r in rows])),
                median_terminal_cash_usdt=float(np.median([r['terminal_cash_usdt'] for r in rows])),
                mean_risk_adjusted_reward_usdt=float(np.mean([r['risk_adjusted_reward_usdt'] for r in rows])),
                worst_terminal_cash_usdt=min(r['terminal_cash_usdt'] for r in rows),
                max_abs_inventory_lots=max(r['max_abs_inventory_lots'] for r in rows),
                per_seed=rows)
        summaries[scenario] = scenario_results
    return summaries, traces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--policy', type=Path, help='Evaluate an exported policy without fitting it again')
    args = parser.parse_args()
    if args.policy:
        policy, values, visits = load_policy(args.policy)
        rewards = []
    else:
        values, visits, rewards = train()
        policy = dict(actions=list(ACTIONS), values=values.tolist(), visits=visits.tolist(),
                      environment_version=1, algorithm='tabular Q-learning', discount=1., learning_rate=0.2,
                      seed=71, train_seeds=list(TRAIN_SEEDS))
    frozen = values.copy()
    scores, traces = evaluate(values)
    if not np.array_equal(frozen, values):
        raise AssertionError('Evaluation mutated policy')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'policy.json').write_text(json.dumps(policy, indent=2) + '\n')
    source_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                     for name in ('learning_market_maker.py', 'learning_book.py', 'clustered_flow.py')}
    report = dict(training='assumed synthetic two-type Hawkes scenarios; no real BTC fit',
        mode='evaluate_loaded_policy' if args.policy else 'train_then_evaluate',
        source_sha256=source_hashes, policy_sha256=hashlib.sha256((args.out / 'policy.json').read_bytes()).hexdigest(),
        seconds=SECONDS, train_seeds=list(TRAIN_SEEDS), test_seeds=list(TEST_SEEDS),
        inventory_cap_lots=CAP, lot_btc=0.01, tick_usdt=0.1, inventory_penalty=PENALTY,
        maker_fee_bps_training=0., taker_fee_bps=0.5,
        training_episode_reward_usdt=rewards, scores=scores)
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    with (args.out / 'trace.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=traces[0])
        writer.writeheader(); writer.writerows(traces)
    print(json.dumps({s: {p: v['mean_risk_adjusted_reward_usdt'] for p, v in rows.items()}
                      for s, rows in scores.items()}, indent=2))


if __name__ == '__main__':
    main()
