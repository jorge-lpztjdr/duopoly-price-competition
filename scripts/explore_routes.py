
"""Explore NYC TLC routes to identify comparable Uber and Lyft samples.

Routes are ranked by the smaller provider trip count, without
using observed fares as a selection criterion.
"""

from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


DATA_PATH = Path("data/raw/fhvhv_tripdata_2025-01.parquet")

# Provisional selection window (start inclusive, end exclusive).
START_DATE = pd.Timestamp("2025-01-13")
END_DATE = pd.Timestamp("2025-01-20")

PROVIDERS = ["HV0003", "HV0005"]

COLUMNS = [
    "hvfhs_license_num",
    "pickup_datetime",
    "PULocationID",
    "DOLocationID",
]


def main():
    """Count trips by route and provider using Parquet batches."""

    counts = Counter()
    parquet = pq.ParquetFile(DATA_PATH)

    for batch in parquet.iter_batches(
        batch_size=100_000,
        columns=COLUMNS,
    ):
        df = batch.to_pandas()

        # Apply the same filters to both providers.
        df = df[
            (df["pickup_datetime"] >= START_DATE)
            & (df["pickup_datetime"] < END_DATE)
            & (df["hvfhs_license_num"].isin(PROVIDERS))
        ]

        df = df.dropna(subset=["PULocationID", "DOLocationID"])


        # Keep routes between two distinct, identified TLC zones.
        df = df[(df["PULocationID"] != df["DOLocationID"]) & df["PULocationID"].between(1, 263) & df["DOLocationID"].between(1, 263)]


        batch_counts = df.groupby(
            ["PULocationID", "DOLocationID", "hvfhs_license_num"]
        ).size()

        counts.update(batch_counts.to_dict())

    # Aggregate trips by origin-destination pair.
    routes = {}

    for (pickup, dropoff, provider), count in counts.items():
        route = (int(pickup), int(dropoff))

        if route not in routes:
            routes[route] = {"HV0003": 0, "HV0005": 0}

        routes[route][provider] += count

    # Prioritise routes with observations from both providers.
    ranked_routes = sorted(
        routes.items(),
        key=lambda item: min(item[1].values()),
        reverse=True,
    )

    # Load official TLC zone names.
    zones = pd.read_csv("data/taxi_zone_lookup.csv")
    zones = zones.set_index("LocationID")

    print("Top 10 candidate routes:\n")

    for (pickup, dropoff), providers in ranked_routes[:10]:

        origin = zones.loc[pickup]
        destination = zones.loc[dropoff]

        print(f"{origin['Zone']} ({origin['Borough']})")
        print(f"    -> {destination['Zone']} ({destination['Borough']})")

        print(
            f"    Uber: {providers['HV0003']} | "
            f"Lyft: {providers['HV0005']}\n"
        )


if __name__ == "__main__":
    main()
