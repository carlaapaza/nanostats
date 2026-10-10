# NanoPlot QC Pipeline

A small command-line pipeline that:

1. Finds Oxford Nanopore FASTQ files in an input directory.
2. Runs NanoPlot once per sample or barcode.
3. Extracts key metrics from every `NanoStats.txt` file.
4. Writes an Excel workbook and a TSV table.
5. Saves the complete terminal output in a timestamped log file.

## Supported input layouts

The pipeline recognizes these filename endings:

- `.fastq`
- `.fq`
- `.fastq.gz`
- `.fq.gz`
- `.fastq.bz2`
- `.fq.bz2`

If reads are inside a directory named `barcodeXX`, all FASTQ chunks in that
directory are analyzed together as one barcode. Otherwise, the filename without
its FASTQ/compression suffix is used as the sample name.

Examples:

```text
reads/
├── barcode01/
│   ├── chunk_001.fastq.gz
│   └── chunk_002.fastq.gz
└── barcode02/
    └── chunk_001.fastq.gz
```

or:

```text
reads/
├── barcode01.fastq.gz
└── barcode02.fq.gz
```

## Installation with Conda

Conda or Mamba is recommended because NanoPlot is distributed through
Bioconda.

```bash
git clone https://github.com/carlaapaza/nanostats.git
cd nanostats

conda env create -f environment.yml
conda activate nanoplot-qc
```

With Mamba, replace `conda env create` with `mamba env create`.

## Usage

```bash
chmod +x run_pipeline.sh

./run_pipeline.sh \
    --input-dir /path/to/reads \
    --output-dir /path/to/qc_results \
    --threads 8
```

Run `./run_pipeline.sh --help` to see all options.

### Restarting and replacing results

Completed samples are skipped when their `NanoStats.txt` already exists. This
makes interrupted runs easy to resume. Use `--force` to replace existing
per-sample NanoPlot directories:

```bash
./run_pipeline.sh \
    --input-dir /path/to/reads \
    --output-dir /path/to/qc_results \
    --threads 8 \
    --force
```

## Outputs

```text
qc_results/
├── nanoplot/
│   ├── barcode01/
│   │   ├── NanoPlot-report.html
│   │   ├── NanoStats.txt
│   │   └── ...
│   └── barcode02/
│       └── ...
├── nanoplot_summary.tsv
├── nanoplot_summary.xlsx
└── nanoplot_qc_YYYYMMDD_HHMMSS_PID.log
```

The summary contains one row per sample/barcode and these columns:

- `Sample`
- `Mean read length`
- `Mean read quality`
- `Median read length`
- `Median read quality`
- `Number of reads`
- `Read length N50`

The Excel workbook includes numeric formatting, filters, alternating row colors,
and a frozen header row.

## Running only the summary step

If NanoPlot reports already exist, regenerate the tables without rerunning
NanoPlot:

```bash
python3 scripts/summarize_nanostats.py \
    --input-dir /path/to/qc_results/nanoplot \
    --output-dir /path/to/qc_results
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```