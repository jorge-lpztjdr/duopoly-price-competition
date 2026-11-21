"""Generate the model figures from saved scenarios."""

import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

from duopoly.model import Params
from duopoly.plots import plot_best_responses, plot_comparative_statics


def main() -> None:
    figures_dir = Path(__file__).resolve().parents[1] / "figures"
    scenarios = json.loads((figures_dir / "scenarios.json").read_text(encoding="utf-8"))
    output_dir = figures_dir / "generated"
    output_dir.mkdir(exist_ok=True)

    f1 = scenarios["F1"]
    f2 = scenarios["F2"]
    f3 = scenarios["F3"]

    fig1 = plot_best_responses(Params(**f1["params"]))
    fig2 = plot_comparative_statics(
        Params(**f2["params"]),
        np.linspace(**f2["s_grid"]),
    )
    fig3 = plot_comparative_statics(
        Params(**f3["params"]),
        np.linspace(**f3["s_grid"]),
        show_shares=True,
    )

    for name, fig in [(f1["name"], fig1), (f2["name"], fig2), (f3["name"], fig3)]:
        fig.savefig(output_dir / f"{name}.pdf", bbox_inches="tight")
        fig.savefig(output_dir / f"{name}.png", dpi=300, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
