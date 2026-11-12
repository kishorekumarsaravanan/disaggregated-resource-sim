"""Step 8: build figures from experiments/results/*.csv.  Usage: python analysis/make_plots.py"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES, FIG = os.path.join(ROOT, "experiments", "results"), os.path.join(ROOT, "analysis", "figures")
os.makedirs(FIG, exist_ok=True)
C_STATIC, C_POOLED, C_REF = "#c0504d", "#2f6db5", "#555555"


def fig1():
    d = pd.read_csv(os.path.join(RES, "exp1_capacity_sweep.csv"))
    ref = d[d.system == "ideal_local"].iloc[0]
    d = d[d.system != "ideal_local"]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    for name, col in (("static", C_STATIC), ("pooled", C_POOLED)):
        s = d[d.system == name].sort_values("mem_total_gb")
        ax[0].plot(s.mem_total_gb, s.makespan_ms, "o-", color=col, label=name)
        ax[1].plot(s.mem_total_gb, s.page_ins, "o-", color=col, label=name)
        ax[2].plot(s.mem_total_gb, s.mem_util_pct, "o-", color=col, label=name)
    ax[0].axhline(ref.makespan_ms, ls="--", color=C_REF, label="ideal local (no fabric, unlimited memory)")
    ax[0].set(title="Time to finish all apps", xlabel="Total memory (GB)", ylabel="Makespan (ms)")
    ax[1].set(title="Page-ins from storage (memory shortfall)", xlabel="Total memory (GB)", ylabel="Page-ins")
    ax[2].set(title="Average memory allocated / total", xlabel="Total memory (GB)", ylabel="Utilization (%)")
    for a in ax:
        a.grid(alpha=.3); a.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig1_capacity_sweep.png"), dpi=150); plt.close(fig)


def fig2():
    d = pd.read_csv(os.path.join(RES, "exp2_fabric_sweep.csv"))
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for a, sweep, label in ((ax[0], "hop_latency_ns", "Per-hop latency (ns)"), (ax[1], "link_gbps", "Link bandwidth (GB/s)")):
        s = d[d.sweep == sweep].copy(); s["value"] = s["value"].astype(float); s = s.sort_values("value")
        a.plot(s.value, s.makespan_overhead_pct, "o-", color=C_POOLED, label="makespan overhead")
        a.plot(s.value, s.mean_op_overhead_pct, "s--", color="#e08a1e", label="mean op latency overhead")
        a.set(xscale="log", yscale="log", xlabel=label, ylabel="Overhead vs ideal local (%)",
              title=f"Sensitivity to {label.split(' (')[0].lower()}")
        a.grid(alpha=.3); a.legend(fontsize=8)
    ax[0].axvline(150, color="gray", ls=":"); ax[1].axvline(32, color="gray", ls=":")
    fig.text(.5, -.02, "dotted line = default configuration", ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig2_fabric_sensitivity.png"), dpi=150, bbox_inches="tight"); plt.close(fig)


def fig3():
    d = pd.read_csv(os.path.join(RES, "exp3_control_plane.csv"))
    g = d[d.sweep == "control_grid"].pivot(index="control_us", columns="reconfig_us", values="makespan_ms")
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    im = ax.imshow(g.values, cmap="YlOrRd", aspect="auto", origin="lower")
    ax.set_xticks(range(len(g.columns)), [f"{c:g}" for c in g.columns]); ax.set_yticks(range(len(g.index)), [f"{i:g}" for i in g.index])
    ax.set(xlabel="Reconfiguration (remap) cost (us)", ylabel="Control message cost (us)", title="Makespan (ms) vs control-plane cost")
    for i in range(g.shape[0]):
        for j in range(g.shape[1]):
            ax.text(j, i, f"{g.values[i, j]:.0f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, label="ms"); fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig3_control_plane.png"), dpi=150); plt.close(fig)


if __name__ == "__main__":
    fig1(); fig2(); fig3(); print("figures written to", FIG)
