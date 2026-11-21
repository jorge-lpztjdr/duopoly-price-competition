"""Mathematical model of price competition in a differentiated duopoly.

Defines demand, profit, best-response and Nash equilibrium calculations.

Authors : Elya Verhoeven, Jorge Sobrino and Jorge López
"""

import numpy as np


class Params:
    """Store the parameters of the differentiated duopoly model."""

    def __init__(self, a: float, delta: float, k: float, s: float, c: float):
        self.a = a
        self.delta = delta
        self.k = k
        self.s = s
        self.c = c


class Equilibrium:
    """Store the Nash equilibrium outcomes for Uber and Lyft.

    Each attribute contains a NumPy array with two elements,
    ordered as [Uber, Lyft].
    """

    def __init__(
        self,
        prices: np.ndarray,
        quantities: np.ndarray,
        margins: np.ndarray,
        profits: np.ndarray,
        shares: np.ndarray,
    ):
        self.prices = prices
        self.quantities = quantities
        self.margins = margins
        self.profits = profits
        self.shares = shares



def validate_params(params: Params) -> None:
    """Validate the mathematical assumptions of the model.

    Checks that all parameters are finite and satisfy:
        k > 0
        s >= 0
        c >= 0
        a > k*c + abs(delta)

    Raises:
        ValueError: If any model assumption is violated.
    """
    values = (params.a, params.delta, params.k, params.s, params.c)
    if not np.all(np.isfinite(values)):
        raise ValueError("All model parameters must be finite.")

    if params.k <= 0:
        raise ValueError("k must be strictly positive.")
    if params.s < 0 or params.c < 0:
        raise ValueError("s and c must be non-negative.")
    if params.a <= params.k * params.c + abs(params.delta):
        raise ValueError("a must be strictly greater than k*c + abs(delta).")


def demand(prices: tuple[float, float], params: Params) -> np.ndarray:
    """Calculate demand for Uber and Lyft at given prices.

    Args:
        prices: Price pair (Uber, Lyft).
        params: Model parameters.

    Returns:
        Array containing non-negative demand for each firm.
    """
    validate_params(params)
    p_u, p_l = prices

    if not np.all(np.isfinite(prices)):
        raise ValueError("Prices must be finite.")
    if p_u < params.c or p_l < params.c:
        raise ValueError("Prices must be at least the marginal cost.")

    relative_price = p_l - p_u
    demand_u = params.a + params.delta - params.k * p_u + params.s * relative_price
    demand_l = params.a - params.delta - params.k * p_l - params.s * relative_price

    return np.maximum(0.0, [demand_u, demand_l])


def profit(prices: tuple[float, float], params: Params) -> np.ndarray:
    """Calculate both firms' profits at given prices.

    Profits are calculated as price-cost margins
    multiplied by their respective demand.

    Returns:
        Array containing profits for Uber and Lyft.
    """
    quantities = demand(prices, params)
    margins = np.asarray(prices) - params.c
    return margins * quantities


def best_response(player: int, rival_price: float, params: Params) -> float:
    """Calculate a firm's optimal price given its rival's price.

    Args:
        player: Firm index (0 for Uber, 1 for Lyft).
        rival_price: Price chosen by the opposing firm.
        params: Model parameters.

    Returns:
        Price maximising the firm's profit.
    """
    validate_params(params)
    if player not in (0, 1):
        raise ValueError("player must be 0 (Uber) or 1 (Lyft).")
    if not np.isfinite(rival_price) or rival_price < params.c:
        raise ValueError("The rival price must be finite and at least the marginal cost.")

    intercept = params.a + params.delta if player == 0 else params.a - params.delta
    zero_demand_price = (intercept + params.s * rival_price) / (params.k + params.s)
    return (params.c + zero_demand_price) / 2


def equilibrium(params: Params) -> Equilibrium:
    """Calculate the unique pure-strategy Nash equilibrium.

    Uses the analytically derived best-response equations.

    Args:
        params: Valid model parameters.

    Returns:
        Equilibrium object containing prices, quantities,
        margins, profits and market shares for both firms.
    """
    validate_params(params)

    mean_margin = (params.a - params.k * params.c) / (2 * params.k + params.s)
    margin_offset = params.delta / (2 * params.k + 3 * params.s)
    margins = np.array([mean_margin + margin_offset, mean_margin - margin_offset])

    prices = params.c + margins
    price_pair = (prices[0], prices[1])
    quantities = demand(price_pair, params)

    return Equilibrium(
        prices=prices,
        quantities=quantities,
        margins=margins,
        profits=profit(price_pair, params),
        shares=quantities / quantities.sum(),
    )
