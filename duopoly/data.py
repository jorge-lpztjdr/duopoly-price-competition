
"""Data acquisition and processing for NYC TLC trip records.

Handles downloading, filtering, validation and descriptive statistics.

Authors : Elya Verhoeven, Jorge Sobrino and Jorge López
"""

from pathlib import Path
import pandas as pd
import numpy as np
import hashlib
from urllib.request import urlopen
import json
import pyarrow.parquet as pq



class SampleSpec:
    """Store the configuration used to select TLC trip records."""

    def __init__(self, source: dict, selection: dict, columns: list[str]):
        self.source = source
        self.selection = selection
        self.columns = columns


def fetch_source(url: str, destination: Path, expected_sha256: str | None = None) -> dict:
    """Download a file and verify its SHA-256 checksum.

    Downloads in chunks to avoid loading the entire file into memory.
    The destination is created only after a successful download.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Prevent overwriting existing downloads.
    if destination.exists():
        raise FileExistsError(f"File already exists: {destination}")

    temporary = destination.with_name(destination.name + ".part")

    if temporary.exists():
        raise FileExistsError(f"Temporary file already exists: {temporary}")

    sha256 = hashlib.sha256()

    try:
        with urlopen(url, timeout=60) as response:
            expected_size = response.headers.get("Content-Length")
            downloaded_size = 0

            with temporary.open("xb") as file:
                while True:
                    chunk = response.read(1024 * 1024)

                    if not chunk:
                        break

                    file.write(chunk)
                    sha256.update(chunk)
                    downloaded_size += len(chunk)

        if expected_size is not None:
            if downloaded_size != int(expected_size):
                raise OSError("Incomplete download")

        actual_sha256 = sha256.hexdigest()

        if expected_sha256 is not None:
            if actual_sha256.lower() != expected_sha256.lower():
                raise ValueError("SHA-256 checksum mismatch")

        temporary.rename(destination)

    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "url": url,
        "path": str(destination),
        "sha256": actual_sha256,
    }



def read_sample_spec(path: Path) -> SampleSpec:
    """Read and validate the sample configuration from JSON.

    Raises:
        ValueError: If the configuration is incomplete or invalid.
    """

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    # Check the structure of the configuration.
    required_sections = {"source", "selection", "columns"}

    if not isinstance(config, dict) or set(config) != required_sections:
        raise ValueError("Invalid sample configuration sections.")

    source = config["source"]
    selection = config["selection"]
    columns = config["columns"]

    if not isinstance(source, dict) or not isinstance(selection, dict):
        raise ValueError("Source and selection must be dictionaries.")

    # Check required fields.
    source_fields = {"name", "url", "filename", "sha256"}

    selection_fields = {
        "start_datetime",
        "end_datetime_exclusive",
        "pickup_location_id",
        "dropoff_location_id",
        "providers",
        "shared_request_flag",
        "shared_match_flag",
        "require_positive_fare",
        "require_positive_distance",
        "require_positive_duration",
    }

    if set(source) != source_fields:
        raise ValueError("Missing or unknown source fields.")

    if set(selection) != selection_fields:
        raise ValueError("Missing or unknown selection fields.")

    # Validate source information.
    if any(not isinstance(value, str) or not value for value in source.values()):
        raise ValueError("Source fields must be non-empty strings.")

    if not source["url"].startswith("https://"):
        raise ValueError("Source URL must use HTTPS.")

    sha256 = source["sha256"]
    if len(sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha256):
        raise ValueError("Invalid SHA-256 checksum.")

    # Validate date range.
    try:
        start = pd.Timestamp(selection["start_datetime"])
        end = pd.Timestamp(selection["end_datetime_exclusive"])
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid selection dates.") from error

    if start.tzinfo is not None or end.tzinfo is not None or start >= end:
        raise ValueError("Selection dates must be ordered and timezone-naive.")

    # Validate geographical zones.
    for key in ["pickup_location_id", "dropoff_location_id"]:
        value = selection[key]
        if type(value) is not int or not 1 <= value <= 263:
            raise ValueError(f"Invalid location ID: {key}")

    # Validate providers.
    providers = selection["providers"]

    if (
        not isinstance(providers, list)
        or len(providers) != 2
        or set(providers) != {"HV0003", "HV0005"}
    ):
        raise ValueError("Providers must be Uber and Lyft.")

    # Validate shared-ride exclusion rules.
    for key in ["shared_request_flag", "shared_match_flag"]:
        if selection[key] != "N":
            raise ValueError(f"{key} must be 'N'.")

    # Our selected population requires positive numeric values.
    for key in [
        "require_positive_fare",
        "require_positive_distance",
        "require_positive_duration",
    ]:
        if selection[key] is not True:
            raise ValueError(f"{key} must be true.")

    # Validate requested columns.
    if (
        not isinstance(columns, list)
        or not all(isinstance(c, str) for c in columns)
        or len(columns) != len(set(columns))
    ):
        raise ValueError("Invalid or duplicated column names.")

    required_columns = {
        "hvfhs_license_num",
        "pickup_datetime",
        "PULocationID",
        "DOLocationID",
        "trip_miles",
        "trip_time",
        "base_passenger_fare",
        "shared_request_flag",
        "shared_match_flag",
    }

    if not required_columns.issubset(columns):
        raise ValueError("Missing required data columns.")

    return SampleSpec(source, selection, columns)




def filter_candidate_trips(df: pd.DataFrame, spec: SampleSpec) -> pd.DataFrame:
    """Select trips matching the specified market.

    Filters by pickup date, origin, destination and provider.
    Does not apply fare, distance, duration or shared-ride rules.

    Args:
        df: Batch of TLC trip records.
        spec: Sample selection configuration.

    Returns:
        DataFrame containing candidate trips.
    """

    selection = spec.selection

    start = pd.Timestamp(selection["start_datetime"])
    end = pd.Timestamp(selection["end_datetime_exclusive"])

    mask = (
        (df["pickup_datetime"] >= start)
        & (df["pickup_datetime"] < end)
        & (df["PULocationID"] == selection["pickup_location_id"])
        & (df["DOLocationID"] == selection["dropoff_location_id"])
        & df["hvfhs_license_num"].isin(selection["providers"])
    )

    return df.loc[mask].copy()




def load_sample(path: Path, spec: SampleSpec) -> tuple[pd.DataFrame, dict]:
    """Load, filter and audit TLC trip records.

    Reads the Parquet file in batches and applies the selection
    and eligibility criteria defined in SampleSpec.

    Returns:
        A DataFrame of eligible trips and a filtering audit.
    """

    parquet = pq.ParquetFile(path)

    # Verify that the required columns are available.
    required_columns = {
        "hvfhs_license_num",
        "pickup_datetime",
        "PULocationID",
        "DOLocationID",
        "base_passenger_fare",
        "trip_miles",
        "trip_time",
        "shared_request_flag",
        "shared_match_flag",
    }

    missing = required_columns - set(spec.columns)
    if missing:
        raise ValueError(f"Missing columns in sample configuration: {sorted(missing)}")

    available = set(parquet.schema_arrow.names)
    missing = set(spec.columns) - available

    if missing:
        raise ValueError(f"Missing Parquet columns: {sorted(missing)}")

    selection = spec.selection
    eligible_batches = []

    # Sequential counts prevent counting an excluded trip twice.
    audit = {
        "total_rows": 0,
        "excluded_outside_market": 0,
        "candidate_rows": 0,
        "excluded_invalid_fare": 0,
        "excluded_invalid_distance": 0,
        "excluded_invalid_duration": 0,
        "excluded_shared_request": 0,
        "excluded_shared_match": 0,
        "eligible_rows": 0,
    }

    for batch in parquet.iter_batches(
        batch_size=100_000,
        columns=spec.columns,
    ):
        df = batch.to_pandas()
        audit["total_rows"] += len(df)

        # Stage 1: Market selection.
        candidates = filter_candidate_trips(df, spec)

        audit["excluded_outside_market"] += len(df) - len(candidates)
        audit["candidate_rows"] += len(candidates)

        # Stage 2: Positive, finite numerical values.
        checks = [
            ("base_passenger_fare", "require_positive_fare", "excluded_invalid_fare"),
            ("trip_miles", "require_positive_distance", "excluded_invalid_distance"),
            ("trip_time", "require_positive_duration", "excluded_invalid_duration"),
        ]

        for column, rule, audit_key in checks:
            if selection[rule]:
                values = pd.to_numeric(candidates[column], errors="coerce")
                valid = np.isfinite(values) & (values > 0)

                audit[audit_key] += int((~valid).sum())
                candidates = candidates.loc[valid]

        # Stage 3: Exclude shared rides.
        shared_checks = [
            ("shared_request_flag", "excluded_shared_request"),
            ("shared_match_flag", "excluded_shared_match"),
        ]

        for column, audit_key in shared_checks:
            valid = candidates[column].eq(selection[column]).fillna(False)

            audit[audit_key] += int((~valid).sum())
            candidates = candidates.loc[valid]

        if not candidates.empty:
            eligible_batches.append(candidates)

    if not eligible_batches:
        raise ValueError("No eligible trips found for the selected market.")

    sample = pd.concat(eligible_batches, ignore_index=True)

    # Both providers must be represented.
    observed_providers = set(sample["hvfhs_license_num"].unique())
    expected_providers = set(selection["providers"])

    if not expected_providers.issubset(observed_providers):
        raise ValueError("The filtered sample does not include all providers.")

    audit["eligible_rows"] = len(sample)
    audit["trips_by_provider"] = {
        provider: int((sample["hvfhs_license_num"] == provider).sum())
        for provider in selection["providers"]
    }

    return sample, audit



def summarise(sample: pd.DataFrame) -> pd.DataFrame:
    """Calculate descriptive statistics for Uber and Lyft.

    Computes trip counts, within-sample shares, base fare quartiles,
    median trip distances and median durations.

    Trip duration is converted from seconds to minutes.
    Base fares are expressed in USD.

    Args:
        sample: Filtered DataFrame containing eligible TLC trips.

    Returns:
        DataFrame with one row per provider.

    Raises:
        ValueError: If the sample is empty or a provider is missing.
    """

    if sample.empty:
        raise ValueError("Cannot summarise an empty sample.")

    providers = {
        "HV0003": "Uber",
        "HV0005": "Lyft",
    }

    if set(sample["hvfhs_license_num"].unique()) != set(providers):
        raise ValueError("The sample must contain Uber and Lyft only.")

    # Avoid modifying the original DataFrame.
    df = sample.copy()

    # TLC trip_time is measured in seconds.
    df["trip_minutes"] = df["trip_time"] / 60

    summary = df.groupby("hvfhs_license_num").agg(
        trips=("base_passenger_fare", "size"),
        fare_q1=("base_passenger_fare", lambda x: x.quantile(0.25)),
        median_fare=("base_passenger_fare", "median"),
        fare_q3=("base_passenger_fare", lambda x: x.quantile(0.75)),
        median_miles=("trip_miles", "median"),
        median_minutes=("trip_minutes", "median"),
    )

    # Calculate shares using the total eligible sample.
    summary["sample_share"] = summary["trips"] / summary["trips"].sum()

    # Replace TLC licence codes with provider names.
    summary.index = summary.index.map(providers)
    summary.index.name = "provider"

    return summary.reset_index()
