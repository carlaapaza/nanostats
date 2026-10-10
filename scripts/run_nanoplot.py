#!/usr/bin/env python3
"""Discover FASTQ files, group them by sample, and run NanoPlot."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


SUPPORTED_SUFFIXES = (
    ".fastq",
    ".fq",
    ".fastq.gz",
    ".fq.gz",
    ".fastq.bz2",
    ".fq.bz2",
)
BARCODE_PATTERN = re.compile(r"barcode\d+", flags=re.IGNORECASE)


def log(message: str) -> None:
    """Print a timestamped message for the pipeline log."""
    stamp = datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z")
    print(f"[{stamp}] {message}", flush=True)


def strip_read_suffix(filename: str) -> str:
    """Remove a supported FASTQ suffix from a filename."""
    lower_name = filename.lower()
    for suffix in sorted(SUPPORTED_SUFFIXES, key=len, reverse=True):
        if lower_name.endswith(suffix):
            return filename[: -len(suffix)]
    return Path(filename).stem


def safe_sample_name(value: str) -> str:
    """Return a filesystem-safe sample identifier."""
    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not safe_value:
        raise ValueError(f"Could not derive a sample name from {value!r}.")
    return safe_value


def sample_name(read_path: Path, input_dir: Path) -> tuple[str, str]:
    """Derive a sample ID, preferring the nearest barcodeXX directory."""
    relative_path = read_path.resolve().relative_to(input_dir.resolve())

    for directory in reversed(relative_path.parts[:-1]):
        if BARCODE_PATTERN.fullmatch(directory):
            return safe_sample_name(directory), directory

    raw_name = strip_read_suffix(read_path.name)
    return safe_sample_name(raw_name), raw_name


def is_supported_read(path: Path) -> bool:
    """Return True when a path has a supported FASTQ extension."""
    lower_name = path.name.lower()
    return path.is_file() and any(
        lower_name.endswith(suffix) for suffix in SUPPORTED_SUFFIXES
    )


def discover_reads(input_dir: Path, recursive: bool) -> list[Path]:
    """Find supported read files in deterministic order."""
    candidates = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return sorted(
        (path.resolve() for path in candidates if is_supported_read(path)),
        key=lambda path: str(path).lower(),
    )


def group_reads(reads: list[Path], input_dir: Path) -> dict[str, list[Path]]:
    """Group read files by barcode directory or filename stem."""
    groups: dict[str, list[Path]] = defaultdict(list)
    original_names: dict[str, str] = {}

    for read_path in reads:
        safe_name, raw_name = sample_name(read_path, input_dir)
        normalized_name = safe_name.casefold()

        if (
            normalized_name in original_names
            and original_names[normalized_name] != raw_name
        ):
            raise ValueError(
                "Sample-name collision after sanitization: "
                f"{original_names[normalized_name]!r} and {raw_name!r} both "
                f"become {safe_name!r}."
            )

        original_names[normalized_name] = raw_name
        groups[safe_name].append(read_path)

    return dict(sorted(groups.items(), key=lambda item: natural_sort_key(item[0])))


def natural_sort_key(value: str) -> list[object]:
    """Sort sample2 before sample10."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    ]


def run_sample(
    sample: str,
    reads: list[Path],
    output_dir: Path,
    threads: int,
    force: bool,
) -> str:
    """Run NanoPlot for one sample and return its execution status."""
    sample_output = output_dir / sample
    stats_file = sample_output / "NanoStats.txt"

    if stats_file.is_file() and not force:
        log(f"Skipping {sample}: a complete NanoPlot result already exists.")
        return "skipped"

    if sample_output.exists():
        if not force:
            raise RuntimeError(
                f"Incomplete output already exists for {sample}: {sample_output}. "
                "Remove it or rerun with --force."
            )
        log(f"Removing the previous output for {sample} because --force was used.")
        shutil.rmtree(sample_output)

    sample_output.mkdir(parents=True, exist_ok=False)

    command = [
        "NanoPlot",
        "--fastq",
        *(str(path) for path in reads),
        "--outdir",
        str(sample_output),
        "--threads",
        str(threads),
    ]

    log(f"Running NanoPlot for {sample} with {len(reads)} read file(s).")
    subprocess.run(command, check=True)

    if not stats_file.is_file():
        raise RuntimeError(
            f"NanoPlot finished for {sample}, but {stats_file} was not created."
        )

    log(f"Finished NanoPlot for {sample}: {sample_output}")
    return "completed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run NanoPlot on all FASTQ files in an input directory."
    )
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing per-sample NanoPlot result.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Search only the top level of the input directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not input_dir.is_dir():
        log(f"ERROR: input directory does not exist: {input_dir}")
        return 2

    if args.threads < 1:
        log("ERROR: --threads must be a positive integer.")
        return 2

    if shutil.which("NanoPlot") is None:
        log("ERROR: NanoPlot was not found in PATH.")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    reads = discover_reads(input_dir, recursive=not args.no_recursive)
    if not reads:
        extensions = ", ".join(SUPPORTED_SUFFIXES)
        log(f"ERROR: no supported FASTQ files were found in {input_dir}.")
        log(f"Supported filename endings: {extensions}")
        return 1

    try:
        groups = group_reads(reads, input_dir)
    except ValueError as error:
        log(f"ERROR: {error}")
        return 1

    log(f"Found {len(reads)} read file(s) in {len(groups)} sample group(s).")

    completed = 0
    skipped = 0

    try:
        for sample, sample_reads in groups.items():
            status = run_sample(
                sample=sample,
                reads=sample_reads,
                output_dir=output_dir,
                threads=args.threads,
                force=args.force,
            )
            completed += status == "completed"
            skipped += status == "skipped"
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        log(f"ERROR: {error}")
        return 1

    log(
        f"NanoPlot stage complete: {completed} completed, "
        f"{skipped} skipped."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
