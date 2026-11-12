# Disaggregated compute / memory / storage / accelerator architecture - simulation

Python + SimPy discrete-event simulation. Time unit: nanoseconds.

```
pip install simpy pandas matplotlib
python tests/test_engine.py            # likewise test_resources / test_fabric / test_manager / test_workloads
python experiments/demo_rebalance.py   # context example: memory moves from App B to App A
python experiments/demo_workloads.py   # 3 apps sharing the pools
python experiments/run_experiments.py all    # exp1, exp2, exp3 -> experiments/results/*.csv
python analysis/make_plots.py                # -> analysis/figures/*.png
```

Layout: `sim/engine.py` (core), `sim/resources/` (node models), `sim/fabric/` (interconnect, remote access),
`sim/manager/` (registry, policies, orchestrator), `sim/workloads/` (apps), `experiments/`, `analysis/`, `REPORT.md`.
