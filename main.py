"""Command-file driven CLI entry point for PS-062 Diagnostic Lab TAT Engine."""

import argparse
from pathlib import Path
import sys

from engine.core import DiagnosticLabEngine


def find_default_data_dir() -> Path:
    candidates = [
        Path("sample_data/T083-PS-062-sample-data"),
        Path("."),
        Path("../sample_data/T083-PS-062-sample-data"),
    ]
    for c in candidates:
        if (c / "tests.csv").exists() and (c / "orders.csv").exists():
            return c
    return Path(".")


def main():
    parser = argparse.ArgumentParser(
        description="PS-062 · Diagnostic Lab Test Ordering and Report TAT Engine"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=find_default_data_dir(),
        help="Directory containing the CSV master files",
    )
    parser.add_argument(
        "--commands",
        type=Path,
        default=None,
        help="Path to commands.txt file (defaults to <data-dir>/commands.txt)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where output CSV files will be generated (default: ./output)",
    )

    args = parser.parse_args()

    data_dir = args.data_dir
    commands_path = args.commands or (data_dir / "commands.txt")
    output_dir = args.output_dir

    if not (data_dir / "tests.csv").exists():
        print(f"Error: tests.csv not found in {data_dir.resolve()}", file=sys.stderr)
        sys.exit(1)

    if not commands_path.exists():
        print(f"Error: commands file not found at {commands_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print(" PS-062 · Diagnostic Lab Test Ordering and Report TAT Engine")
    print("=" * 80)
    print(f"Data Directory:    {data_dir.resolve()}")
    print(f"Commands File:     {commands_path.resolve()}")
    print(f"Output Directory:  {output_dir.resolve()}")
    print("-" * 80)

    # Initialize Engine
    print("Initializing diagnostic lab engine and loading master records...")
    engine = DiagnosticLabEngine(data_dir)
    print(f"Loaded {len(engine.tests)} tests, {len(engine.panels)} panels, {len(engine.labs)} labs,")
    print(f"{len(engine.phlebotomists)} phlebotomists, and {len(engine.orders)} orders.")
    print("-" * 80)

    # Process Commands
    print("Executing event commands from commands file...")
    engine.process_command_file(commands_path)
    print("-" * 80)

    # Export Reports
    print("Exporting canonical evaluation CSV reports...")
    engine.export_all_reports(output_dir)
    print("=" * 80)
    print(" Execution completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
