#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
THREADS="${THREADS:-8}"

INPUT_DIR=""
OUTPUT_DIR=""
FORCE=0
RECURSIVE=1

usage() {
    cat <<'EOF'
Run NanoPlot on FASTQ reads and build TSV/XLSX summary tables.

Usage:
  ./run_pipeline.sh --input-dir PATH --output-dir PATH [options]

Required arguments:
  -i, --input-dir PATH     Directory containing FASTQ files.
  -o, --output-dir PATH    Directory in which results will be written.

Options:
  -t, --threads INT        Threads passed to NanoPlot (default: 8).
      --force              Replace existing per-sample NanoPlot results.
      --no-recursive       Search only the top level of the input directory.
  -h, --help               Show this help message.

Environment variables:
  THREADS                  Alternative way to set the thread count.
  PYTHON_BIN               Python executable to use (default: python3).
EOF
}

log() {
    printf '[%s] %s\n' "$(date '+%A %Y-%m-%d %H:%M:%S %Z')" "$*"
}

while (($# > 0)); do
    case "$1" in
        -i|--input-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value." >&2; exit 2; }
            INPUT_DIR="$2"
            shift 2
            ;;
        -o|--output-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value." >&2; exit 2; }
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -t|--threads)
            [[ $# -ge 2 ]] || { echo "ERROR: $1 requires a value." >&2; exit 2; }
            THREADS="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --no-recursive)
            RECURSIVE=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$INPUT_DIR" || -z "$OUTPUT_DIR" ]]; then
    echo "ERROR: --input-dir and --output-dir are required." >&2
    usage >&2
    exit 2
fi

if [[ ! "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: --threads must be a positive integer." >&2
    exit 2
fi

mkdir -p "$OUTPUT_DIR"

RUN_ID="$(date '+%Y%m%d_%H%M%S')_$$"
LOG_FILE="$OUTPUT_DIR/nanoplot_qc_${RUN_ID}.log"
START_SECONDS=$SECONDS

finish() {
    local status=$?
    local elapsed=$((SECONDS - START_SECONDS))
    local hours=$((elapsed / 3600))
    local minutes=$(((elapsed % 3600) / 60))
    local seconds=$((elapsed % 60))

    if ((status == 0)); then
        log "Pipeline completed successfully."
    else
        log "Pipeline failed with exit status $status."
    fi

    log "Total runtime: ${hours}h ${minutes}m ${seconds}s"
    log "Log file: $LOG_FILE"
}

pipeline_main() {
    log "Starting NanoPlot QC pipeline."
    log "Input directory: $INPUT_DIR"
    log "Output directory: $OUTPUT_DIR"
    log "Threads: $THREADS"
    log "Recursive search: $([[ $RECURSIVE -eq 1 ]] && echo yes || echo no)"

    command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
        log "ERROR: $PYTHON_BIN was not found in PATH."
        return 1
    }

    command -v NanoPlot >/dev/null 2>&1 || {
        log "ERROR: NanoPlot was not found in PATH. Activate the provided environment first."
        return 1
    }

    log "Python version: $($PYTHON_BIN --version 2>&1)"
    log "NanoPlot version: $(NanoPlot --version 2>&1 | head -n 1)"

    NANOPLOT_ARGS=(
        --input-dir "$INPUT_DIR"
        --output-dir "$OUTPUT_DIR/nanoplot"
        --threads "$THREADS"
    )

    if ((FORCE == 1)); then
        NANOPLOT_ARGS+=(--force)
    fi

    if ((RECURSIVE == 0)); then
        NANOPLOT_ARGS+=(--no-recursive)
    fi

    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/run_nanoplot.py" "${NANOPLOT_ARGS[@]}"

    "$PYTHON_BIN" "$SCRIPT_DIR/scripts/summarize_nanostats.py" \
        --input-dir "$OUTPUT_DIR/nanoplot" \
        --output-dir "$OUTPUT_DIR"

    log "NanoPlot reports: $OUTPUT_DIR/nanoplot"
    log "TSV summary: $OUTPUT_DIR/nanoplot_summary.tsv"
    log "Excel summary: $OUTPUT_DIR/nanoplot_summary.xlsx"
}

# Stream all output to the terminal and save the same content in one log file.
set +e
(
    set -Eeuo pipefail
    trap finish EXIT
    pipeline_main
) 2>&1 | tee -a "$LOG_FILE"
PIPELINE_STATUS=${PIPESTATUS[0]}
set -e

exit "$PIPELINE_STATUS"
