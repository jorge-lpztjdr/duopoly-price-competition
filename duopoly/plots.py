
"""
Reproducible visualisations of theoretical and empirical results.

Authors : Elya Verhoeven, Jorge Sobrino and Jorge López
"""

import matplotlib.pyplot as plt

from collections.abc import Sequence

import pandas as pd
from matplotlib.figure import Figure

from duopoly.model import Params, best_response, equilibrium


def plot_best_responses(params: Params) -> Figure:
    """Plot both firms' best-response functions and their intersection.

    Args:
        params: Parameters of the differentiated duopoly model.

    Returns:
        Matplotlib figure showing both best-response curves
        and the Nash equilibrium.
    """
    eq = equilibrium(params)
    upper_price = params.c + 2 * max(eq.margins)
    rival_prices = [params.c, upper_price]

    uber_prices = [best_response(0, price, params) for price in rival_prices]
    lyft_prices = [best_response(1, price, params) for price in rival_prices]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(uber_prices, rival_prices, label="Uber best response")
    ax.plot(rival_prices, lyft_prices, linestyle="--", label="Lyft best response")
    ax.scatter(*eq.prices, color="black", zorder=3, label="Nash equilibrium")

    ax.set(
        xlabel="Uber price",
        ylabel="Lyft price",
        xlim=(params.c, upper_price),
        ylim=(params.c, upper_price),
        title="Best responses in price competition",
    )
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_comparative_statics(
    params: Params,
    s_values: Sequence[float],
    *,
    show_shares: bool = False,
) -> Figure:
    """Plot equilibrium outcomes for different price sensitivities.

    Only parameter s varies. Parameters a, delta, k and c
    remain constant across all scenarios.

    Args:
        params: Baseline model parameters.
        s_values: Values of relative-price sensitivity to evaluate.

    Returns:
        Matplotlib figure comparing equilibrium outcomes.
    """
    if len(s_values) < 2:
        raise ValueError("Provide at least two values of s.")
    if any(left >= right for left, right in zip(s_values, s_values[1:])):
        raise ValueError("Values of s must be strictly increasing.")

    outcomes = []
    for s in s_values:
        scenario = Params(a=params.a, delta=params.delta, k=params.k, s=s, c=params.c)
        outcomes.append(equilibrium(scenario))

    fig, (price_ax, outcome_ax) = plt.subplots(1, 2, figsize=(9, 4), sharex=True)

    firms = [(0, "Both firms", "-")]
    if params.delta != 0:
        firms = [(0, "Uber", "-"), (1, "Lyft", "--")]

    for index, label, style in firms:
        prices = [outcome.prices[index] for outcome in outcomes]
        if show_shares:
            values = [100 * outcome.shares[index] for outcome in outcomes]
        else:
            values = [outcome.profits[index] for outcome in outcomes]

        price_ax.plot(s_values, prices, linestyle=style, label=label)
        outcome_ax.plot(s_values, values, linestyle=style, label=label)

    price_ax.set_ylabel("Equilibrium price per firm")
    if show_shares:
        outcome_ax.set_ylabel("Share of duopoly demand (%)")
        outcome_ax.set_ylim(0, 100)
    else:
        outcome_ax.set_ylabel("Equilibrium profit per firm")

    for ax in (price_ax, outcome_ax):
        ax.set_xlabel("Relative-price sensitivity, s")
        ax.grid(alpha=0.25)
    price_ax.legend()

    fig.tight_layout()
    return fig



def plot_fares(sample: pd.DataFrame) -> Figure:
    """Plot observed base passenger fares for Uber and Lyft.

    Uses a boxplot to compare medians, quartiles and dispersion.
    Outliers are hidden for visual clarity, but remain in the data.

    Args:
        sample: Filtered TLC trip records.

    Returns:
        Matplotlib Figure containing the fare comparison.
    """

    providers = {
        "HV0003": "Uber",
        "HV0005": "Lyft",
    }

    fares = []
    labels = []

    for code, name in providers.items():
        values = sample.loc[
            sample["hvfhs_license_num"] == code,
            "base_passenger_fare",
        ].dropna()

        if values.empty:
            raise ValueError(f"No observations for {name}")

        fares.append(values)
        labels.append(f"{name}\n(n={len(values):,})")

    fig, ax = plt.subplots(figsize=(7, 5))

    ax.boxplot(
        fares,
        tick_labels=labels,
        showfliers=False,
        patch_artist=True,
    )

    ax.set_title("Base Passenger Fares: Uber vs Lyft")
    ax.set_ylabel("Base passenger fare (USD)")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    return fig
