# tcxpower

A command-line tool that reads one or two Garmin `.tcx` files and generates a
self-contained, interactive HTML graph of power (watts) against time.

- **One file** – power trace, 30 s rolling average, and summary stats.
- **Two files** – both traces aligned by absolute timestamp, plus a difference
  channel (meter 1 − meter 2), useful for comparing two power meters recorded
  during the same ride.

## Requirements

- Python 3.10 or newer (uses `list[dict]` / `int | None` type syntax)
- No third-party Python packages (standard library only)
- A web browser with internet access to view the output (the HTML loads
  [Chart.js](https://www.chartjs.org/) from the jsDelivr CDN)

## Usage

```
python3 tcx_power_graph.py TCX_FILE [TCX_FILE] [-o OUTPUT] [--title TITLE]
                           [--labels LABEL LABEL]
```

Show the built-in help with:

```
python3 tcx_power_graph.py --help
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TCX_FILE` | Yes | Path to a `.tcx` file. Give **one** file for a single-meter graph, or **two** files for a comparison. More than two is an error. |
| `-o`, `--output OUTPUT` | No | Path of the HTML file to write. Default: the first TCX file's path with the extension changed to `.html` (e.g. `ride.tcx` → `ride.html`). |
| `--title TITLE` | No | Title shown on the page and in the browser tab. Default: the first file's name without extension for a single file, or `Power Meter Comparison` for two files. |
| `--labels LABEL LABEL` | No | Display names for the two meters (comparison mode only). Must be exactly two values, otherwise it is ignored and the file names (without extension) are used. Quote names containing spaces. |

> **Note:** `--labels` is placed after the TCX files in the examples below. Because
> both `tcx_files` and `--labels` accept multiple values, put other options
> (`-o`, `--title`) or a `--` separator between them if you list them in a
> different order, e.g. `--labels "A" "B" -- a.tcx b.tcx`.

## Input requirements

- Standard Garmin TCX (`TrainingCenterDatabase/v2`) files.
- Trackpoints must contain a `<Time>` element and a power value in the
  activity extension (`<ns3:Watts>`). Trackpoints missing either are skipped.
- If a file contains no power data, the script exits with an error.

## Output

A single HTML file containing:

- **Stat cards** – average power (non-zero samples only), max power, and
  normalised power (NP, from a 30 s rolling average raised to the 4th power).
  Single-file mode also shows total duration.
- **Chart** – raw power plus a 30 s rolling average per meter.
- **Comparison mode only** – a dashed red difference line (meter 1 − meter 2,
  30 s average) on a secondary right-hand axis, and separate stats per meter.
  Traces are placed on a shared 1-second grid starting at the earliest
  timestamp across both files.

Open the file in any browser; hover the chart to see values at a point in time.

## Examples

### Single file

Graph one ride; writes `ride.html` next to `ride.tcx`:

```
python3 tcx_power_graph.py ride.tcx
```

Choose the output path and title:

```
python3 tcx_power_graph.py ride.tcx -o graphs/sunday_ride.html --title "Sunday Long Ride"
```

### Compare two power meters

Compare two recordings of the same ride; writes `assioma.html`
(named after the first file) with default labels taken from the file names:

```
python3 tcx_power_graph.py assioma.tcx rally.tcx
```

Give the meters friendly names, a title, and an output file:

```
python3 tcx_power_graph.py assioma.tcx rally.tcx \
    -o compare.html \
    --title "Assioma vs Rally – 2026-07-06" \
    --labels "Favero Assioma" "Garmin Rally"
```

If you prefer to put the labels last, use `--` to end option parsing before the
positional files, or place the files first (as above) and the options after them.

### Sample output

The repository includes example generated graphs: `20260517.html`,
`compare_20260706.html` and `compare_20262006.html`.

## Console output

The script prints progress as it runs:

```
Parsing assioma.tcx…
  3,612 points  |  2026-07-06
Parsing rally.tcx…
  3,598 points  |  2026-07-06
Written to compare.html
```

## Errors

| Message | Cause |
|---------|-------|
| `Error: at most two TCX files are supported.` | More than two files were passed. |
| `Error: file not found: <path>` | A given path does not exist. |
| `Error: no power (Watts) data found in <path>` | The file has no usable `Time` + `Watts` trackpoints. |
