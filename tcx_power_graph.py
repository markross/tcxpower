#!/usr/bin/env python3
"""CLI tool to parse TCX files and generate an HTML power-vs-time graph.

Supports one or two TCX files. With two files the traces are aligned by
absolute timestamp and a difference channel (meter1 − meter2) is shown on
a secondary axis.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

NS = {
    'tcx': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2',
    'ns3': 'http://www.garmin.com/xmlschemas/ActivityExtension/v2',
}

# Palette: [raw, 30s-avg] per meter; diff line
COLOURS = [
    ('rgba(99,179,237,0.5)',  '#63b3ed'),   # blue  – meter 1
    ('rgba(154,230,180,0.5)', '#9ae6b4'),   # green – meter 2
]
DIFF_COLOUR = '#fc8181'   # red for difference

SINGLE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e0e0e0;padding:24px}}
    h1{{font-size:1.4rem;font-weight:600;margin-bottom:4px}}
    .meta{{font-size:.85rem;color:#888;margin-bottom:24px}}
    .stats{{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}}
    .stat{{background:#1c1f2e;border-radius:8px;padding:14px 20px;min-width:130px}}
    .stat-label{{font-size:.75rem;color:#888;text-transform:uppercase;letter-spacing:.05em}}
    .stat-value{{font-size:1.6rem;font-weight:700;color:#f0f0f0}}
    .stat-unit{{font-size:.8rem;color:#888}}
    .chart-wrap{{background:#1c1f2e;border-radius:8px;padding:20px;margin-bottom:20px}}
    canvas{{max-height:420px}}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">{meta}</p>
  <div class="stats">{stats_html}</div>
  <div class="chart-wrap"><canvas id="chart"></canvas></div>
  <script>
  {js}
  </script>
</body>
</html>
"""

COMPARE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e0e0e0;padding:24px}}
    h1{{font-size:1.4rem;font-weight:600;margin-bottom:4px}}
    .meta{{font-size:.85rem;color:#888;margin-bottom:24px}}
    .meter-group{{margin-bottom:24px}}
    .meter-title{{font-size:1rem;font-weight:600;margin-bottom:10px;padding-left:4px;border-left:3px solid {c1_solid}}}
    .meter-title.m2{{border-color:{c2_solid}}}
    .stats{{display:flex;gap:16px;flex-wrap:wrap}}
    .stat{{background:#1c1f2e;border-radius:8px;padding:14px 20px;min-width:130px}}
    .stat-label{{font-size:.75rem;color:#888;text-transform:uppercase;letter-spacing:.05em}}
    .stat-value{{font-size:1.6rem;font-weight:700;color:#f0f0f0}}
    .stat-unit{{font-size:.8rem;color:#888}}
    .chart-wrap{{background:#1c1f2e;border-radius:8px;padding:20px;margin-bottom:20px}}
    canvas{{max-height:460px}}
    .diff-note{{font-size:.8rem;color:#888;margin-top:8px;padding-left:4px}}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">{meta}</p>
  {meters_html}
  <div class="chart-wrap"><canvas id="chart"></canvas></div>
  <p class="diff-note">Difference = Meter 1 − Meter 2 (30 s avg), shown on right axis</p>
  <script>
  {js}
  </script>
</body>
</html>
"""


def parse_tcx(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    points = []
    for tp in root.iter('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Trackpoint'):
        time_el = tp.find('tcx:Time', NS)
        watts_el = tp.find('.//ns3:Watts', NS)
        if time_el is None or watts_el is None:
            continue
        try:
            t = datetime.fromisoformat(time_el.text.replace('Z', '+00:00'))
            w = int(watts_el.text)
        except (ValueError, TypeError):
            continue
        points.append({'time': t, 'watts': w})
    return points


def rolling_avg(values: list[int | None], window: int) -> list[float | None]:
    result: list[float | None] = []
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        result.append(round(sum(chunk) / len(chunk), 1) if chunk else None)
    return result


def normalised_power(values: list[int]) -> int:
    if len(values) < 30:
        return 0
    avgs = rolling_avg(values, 30)
    fourth = [a ** 4 for a in avgs if a is not None]
    return round((sum(fourth) / len(fourth)) ** 0.25) if fourth else 0


def fmt_hms(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def fmt_elapsed(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f'{h}h {m:02d}m' if h else f'{m}m {s:02d}s'


def stat_card(label: str, value: str, unit: str = '') -> str:
    unit_html = f'<span class="stat-unit"> {unit}</span>' if unit else ''
    return (
        f'<div class="stat">'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}{unit_html}</div>'
        f'</div>'
    )


def stats_for(watts: list[int]) -> tuple[int, int, int]:
    non_zero = [w for w in watts if w > 0]
    avg = round(sum(non_zero) / len(non_zero)) if non_zero else 0
    return avg, max(watts), normalised_power(watts)


def js_array(values: list) -> str:
    return '[' + ','.join('null' if v is None else str(v) for v in values) + ']'


def js_str_array(values: list[str]) -> str:
    return '[' + ','.join(f'"{v}"' for v in values) + ']'


# ---------------------------------------------------------------------------
# Single-file output
# ---------------------------------------------------------------------------

def build_single(points: list[dict], title: str) -> str:
    t0 = points[0]['time']
    elapsed = [(p['time'] - t0).total_seconds() for p in points]
    watts = [p['watts'] for p in points]
    avg_p, max_p, np_val = stats_for(watts)

    cards = (
        stat_card('Avg Power', str(avg_p), 'W') +
        stat_card('Max Power', str(max_p), 'W') +
        stat_card('Norm Power', str(np_val), 'W') +
        stat_card('Duration', fmt_hms(elapsed[-1]))
    )
    meta = f'{t0.strftime("%Y-%m-%d")}  •  {len(points):,} data points'

    raw_col, avg_col = COLOURS[0]
    js = f"""
    const labels = {js_str_array([fmt_elapsed(e) for e in elapsed])};
    new Chart(document.getElementById('chart'), {{
      type: 'line',
      data: {{
        labels,
        datasets: [
          {{
            label: 'Power (W)',
            data: {js_array(watts)},
            borderColor: '{raw_col}',
            backgroundColor: 'rgba(99,179,237,0.08)',
            borderWidth: 1, pointRadius: 0, fill: true, tension: 0, order: 2,
          }},
          {{
            label: '30 s avg (W)',
            data: {js_array(rolling_avg(watts, 30))},
            borderColor: '{avg_col}',
            borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3, order: 1,
          }},
        ],
      }},
      options: {{
        animation: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ labels: {{ color: '#ccc' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#888', maxTicksLimit: 12, maxRotation: 0 }}, grid: {{ color: '#2a2d3e' }} }},
          y: {{ title: {{ display: true, text: 'Power (W)', color: '#888' }}, ticks: {{ color: '#888' }}, grid: {{ color: '#2a2d3e' }}, min: 0 }},
        }},
      }},
    }});
    """

    return SINGLE_TEMPLATE.format(title=title, meta=meta, stats_html=cards, js=js)


# ---------------------------------------------------------------------------
# Two-file comparison output
# ---------------------------------------------------------------------------

def align_to_grid(points: list[dict], t0: datetime, duration_s: int) -> list[int | None]:
    """Map points onto a 1-second integer grid relative to t0."""
    lookup: dict[int, int] = {}
    for p in points:
        offset = round((p['time'] - t0).total_seconds())
        lookup[offset] = p['watts']
    return [lookup.get(s) for s in range(duration_s + 1)]


def build_compare(points_a: list[dict], points_b: list[dict],
                  label_a: str, label_b: str, title: str) -> str:
    t0 = min(points_a[0]['time'], points_b[0]['time'])
    end = max(points_a[-1]['time'], points_b[-1]['time'])
    duration_s = round((end - t0).total_seconds())

    grid_a = align_to_grid(points_a, t0, duration_s)
    grid_b = align_to_grid(points_b, t0, duration_s)

    avg30_a = rolling_avg(grid_a, 30)
    avg30_b = rolling_avg(grid_b, 30)

    diff = [
        round(a - b, 1) if a is not None and b is not None else None
        for a, b in zip(avg30_a, avg30_b)
    ]

    labels = [fmt_elapsed(s) for s in range(duration_s + 1)]

    watts_a = [w for w in grid_a if w is not None]
    watts_b = [w for w in grid_b if w is not None]
    avg_a, max_a, np_a = stats_for(watts_a)
    avg_b, max_b, np_b = stats_for(watts_b)

    c1_raw, c1_solid = COLOURS[0]
    c2_raw, c2_solid = COLOURS[1]

    def meter_block(label: str, cls: str, avg: int, mx: int, np: int,
                    colour: str, n: int) -> str:
        return (
            f'<div class="meter-group">'
            f'<div class="meter-title {cls}">{label} <small style="font-weight:400;color:#888">({n:,} pts)</small></div>'
            f'<div class="stats">'
            f'{stat_card("Avg Power", str(avg), "W")}'
            f'{stat_card("Max Power", str(mx), "W")}'
            f'{stat_card("Norm Power", str(np), "W")}'
            f'</div></div>'
        )

    meters_html = (
        meter_block(label_a, '', avg_a, max_a, np_a, c1_solid, len(watts_a)) +
        meter_block(label_b, 'm2', avg_b, max_b, np_b, c2_solid, len(watts_b))
    )

    diff_non_none = [d for d in diff if d is not None]
    diff_min = round(min(diff_non_none)) if diff_non_none else -50
    diff_max = round(max(diff_non_none)) if diff_non_none else 50

    meta = f'{t0.strftime("%Y-%m-%d")}  •  aligned by absolute timestamp'

    js = f"""
    const labels = {js_str_array(labels)};
    new Chart(document.getElementById('chart'), {{
      type: 'line',
      data: {{
        labels,
        datasets: [
          {{
            label: '{label_a} raw (W)',
            data: {js_array(grid_a)},
            borderColor: '{c1_raw}',
            backgroundColor: 'rgba(99,179,237,0.06)',
            borderWidth: 1, pointRadius: 0, fill: true, tension: 0,
            yAxisID: 'yPower', order: 4,
          }},
          {{
            label: '{label_a} 30 s avg (W)',
            data: {js_array(avg30_a)},
            borderColor: '{c1_solid}',
            borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3,
            yAxisID: 'yPower', order: 2,
          }},
          {{
            label: '{label_b} raw (W)',
            data: {js_array(grid_b)},
            borderColor: '{c2_raw}',
            backgroundColor: 'rgba(154,230,180,0.06)',
            borderWidth: 1, pointRadius: 0, fill: true, tension: 0,
            yAxisID: 'yPower', order: 3,
          }},
          {{
            label: '{label_b} 30 s avg (W)',
            data: {js_array(avg30_b)},
            borderColor: '{c2_solid}',
            borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3,
            yAxisID: 'yPower', order: 1,
          }},
          {{
            label: 'Diff M1−M2 30 s avg (W)',
            data: {js_array(diff)},
            borderColor: '{DIFF_COLOUR}',
            borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3,
            borderDash: [4, 3],
            yAxisID: 'yDiff', order: 0,
          }},
        ],
      }},
      options: {{
        animation: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ labels: {{ color: '#ccc' }} }} }},
        scales: {{
          x: {{
            ticks: {{ color: '#888', maxTicksLimit: 12, maxRotation: 0 }},
            grid: {{ color: '#2a2d3e' }},
          }},
          yPower: {{
            type: 'linear', position: 'left',
            title: {{ display: true, text: 'Power (W)', color: '#888' }},
            ticks: {{ color: '#888' }},
            grid: {{ color: '#2a2d3e' }},
            min: 0,
          }},
          yDiff: {{
            type: 'linear', position: 'right',
            title: {{ display: true, text: 'Difference (W)', color: '{DIFF_COLOUR}' }},
            ticks: {{ color: '{DIFF_COLOUR}' }},
            grid: {{ drawOnChartArea: false }},
            min: {diff_min - 10},
            max: {diff_max + 10},
          }},
        }},
      }},
    }});
    """

    return COMPARE_TEMPLATE.format(
        title=title,
        meta=meta,
        meters_html=meters_html,
        c1_solid=c1_solid,
        c2_solid=c2_solid,
        js=js,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Graph power from one or two Garmin TCX files.',
    )
    parser.add_argument('tcx_files', type=Path, nargs='+', metavar='TCX_FILE',
                        help='One or two .tcx files')
    parser.add_argument('-o', '--output', type=Path,
                        help='Output HTML file (default: first file with .html)')
    parser.add_argument('--title', help='Chart title')
    parser.add_argument('--labels', nargs='+', metavar='LABEL',
                        help='Names for each meter, e.g. --labels "Favero Assioma" "Garmin Rally"')
    args = parser.parse_args()

    if len(args.tcx_files) > 2:
        sys.exit('Error: at most two TCX files are supported.')

    all_points = []
    for path in args.tcx_files:
        if not path.exists():
            sys.exit(f'Error: file not found: {path}')
        print(f'Parsing {path}…')
        pts = parse_tcx(path)
        if not pts:
            sys.exit(f'Error: no power (Watts) data found in {path}')
        print(f'  {len(pts):,} points  |  {pts[0]["time"].date()}')
        all_points.append(pts)

    output = args.output or args.tcx_files[0].with_suffix('.html')
    title = args.title or ('Power Meter Comparison' if len(all_points) == 2
                           else args.tcx_files[0].stem)

    if len(all_points) == 1:
        html = build_single(all_points[0], title)
    else:
        default_labels = [p.stem for p in args.tcx_files]
        labels = args.labels if args.labels and len(args.labels) == 2 else default_labels
        html = build_compare(all_points[0], all_points[1], labels[0], labels[1], title)

    output.write_text(html, encoding='utf-8')
    print(f'Written to {output}')


if __name__ == '__main__':
    main()
