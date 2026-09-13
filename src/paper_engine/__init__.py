"""
Paper Engine V1: sequential causal simulated research engine.

Greenfield research module (PAPER_ENGINE_V1_SPEC.md, PE-0 approved).
Build order is gated: PE-1 (sequential event iterator + causal state)
first; each later gate (signal, latency, execution, outcomes, costs,
metrics, ledger, replay) starts only after the previous gate's tests pass.

PE-1 scope (approved):
  - sequential iterator over validated intermediate event tapes
  - exact event ordering preserved
  - source_hour / episode identity preserved
  - only causal state available at each event
  - no signal generation, no latency model, no execution, no costs,
    no outcome optimization
"""