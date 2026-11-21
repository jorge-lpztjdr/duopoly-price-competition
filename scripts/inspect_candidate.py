
"""Inspect the candidate TLC route before finalising sample filters."""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DATA_PATH = Path("data/raw/fhvhv_tripdata_2025-01.parquet")

COLUMNS = [
    "hvfhs_license_num",
    "pickup_datetime",
    "PULocationID",
    "DOLocationID",
    "trip_miles",
    "trip_time",
    "base_passenger_fare",
    "shared_request_flag",
    "shared_match_flag",
]

selected_batches = []

parquet = pq.ParquetFile(DATA_PATH)

for batch in parquet.iter_batches(
    batch_size=100_000,
    columns=COLUMNS,
):
    df = batch.to_pandas()

    mask = (
        (df["pickup_datetime"] >= "2025-01-13")
        & (df["pickup_datetime"] < "2025-01-20")
        & (df["PULocationID"] == 255)
        & (df["DOLocationID"] == 112)
        & df["hvfhs_license_num"].isin(["HV0003", "HV0005"])
    )

    selected = df.loc[mask]

    if not selected.empty:
        selected_batches.append(selected)

if not selected_batches:
    raise ValueError("No trips found for the candidate route.")

sample = pd.concat(selected_batches, ignore_index=True)

print("\nOriginal counts:")
print(sample["hvfhs_license_num"].value_counts())

# Inspect shared-ride indicators before defining exclusions.
print("\nShared ride flag combinations:")
print(
    sample.groupby(
        ["hvfhs_license_num", "shared_request_flag", "shared_match_flag"],
        dropna=False,
    ).size()
)

# Evaluate basic eligibility without applying shared-ride exclusions.
numeric = sample[["trip_miles", "trip_time", "base_passenger_fare"]]

eligible = (
    numeric.notna().all(axis=1)
    & np.isfinite(numeric).all(axis=1)
    & numeric.gt(0).all(axis=1)
)

clean = sample.loc[eligible].copy()
clean["trip_minutes"] = clean["trip_time"] / 60

print("\nCounts after basic eligibility checks:")
print(clean["hvfhs_license_num"].value_counts())

print("\nTrip composition by provider:")
print(
    clean.groupby("hvfhs_license_num").agg(
        trips=("trip_miles", "size"),
        median_miles=("trip_miles", "median"),
        median_minutes=("trip_minutes", "median"),
    ).round(2)
)
