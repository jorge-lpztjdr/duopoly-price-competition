
"""Run the TLC data processing pipeline.

Reads the sample configuration, filters the source data,
and exports descriptive statistics and filtering records.
"""

import json
from pathlib import Path
import hashlib
import matplotlib.pyplot as plt

from duopoly.plots import plot_fares
from duopoly.data import read_sample_spec, load_sample, summarise


CONFIG_PATH = Path("data/sample.json")
RAW_DIRECTORY = Path("data/raw")
OUTPUT_DIRECTORY = Path("data/processed")


def main():
    """Process TLC trip records and save reproducible outputs."""

    # 1. Read sample configuration.
    spec = read_sample_spec(CONFIG_PATH)

    # 2. Locate the source data.
    source_path = RAW_DIRECTORY / spec.source["filename"]

    if not source_path.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    # Verify that the local file matches the selected data source.
    with source_path.open("rb") as file:
        actual_sha256 = hashlib.file_digest(file, "sha256").hexdigest()

    expected_sha256 = spec.source["sha256"]

    if actual_sha256 != expected_sha256:
        raise ValueError(
            "Source file checksum mismatch. "
            "The local data does not match sample.json."
        )

    print("Source file integrity verified.")

    # 3. Load and filter trip records.
    print("Processing TLC trip records...")
    sample, audit = load_sample(source_path, spec)

    # 4. Calculate descriptive statistics.
    summary = summarise(sample)

    # 5. Check that the audit and summary are consistent.
    if summary["trips"].sum() != audit["eligible_rows"]:
        raise ValueError("Summary counts do not match the filtering audit.")

    # 6. Create output directory.
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # 7. Save descriptive statistics.
    summary.to_csv(OUTPUT_DIRECTORY / "summary.csv", index=False)

    # 8. Save filtering audit.
    with (OUTPUT_DIRECTORY / "filter_audit.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(audit, file, indent=4)

    # Generate and save the empirical fare distribution figure.
    figures_dir = Path("figures/generated")
    figures_dir.mkdir(parents=True, exist_ok=True)

    fig = plot_fares(sample)

    fig.savefig(
        figures_dir / "fare_distribution.pdf",
        bbox_inches="tight",
    )

    fig.savefig(
        figures_dir / "fare_distribution.png",
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(fig)

    print("\nProcessing completed successfully.")
    print(f"Eligible trips: {audit['eligible_rows']}")
    print("\nDescriptive statistics:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
