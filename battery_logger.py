"""Bounded read-only battery recording. Never changes keyboard settings."""
import argparse
import csv
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
UTC = dt.timezone.utc


def read_json(command):
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None, 'read_timeout'
    if result.returncode:
        return None, (result.stderr.strip() or f'exit_{result.returncode}')[:400]
    try:
        return json.loads(result.stdout), None
    except (json.JSONDecodeError, TypeError):
        return None, 'invalid_reader_output'


def percent(value):
    return type(value) is int and 0 <= value <= 100


def collect(start):
    row = {'at_utc': dt.datetime.now(UTC).isoformat(),
           'elapsed_seconds': round(time.time() - start, 2),
           'battery_percent': None, 'cached_report_percent': None,
           'standard_report_percent': None, 'sensor_average_raw': None,
           'status': 'error', 'error': None}
    reading, error = read_json([str(ROOT / 'build/keychron-battery'), 'sample'])
    if error or not reading or not percent(reading.get('battery_percent')):
        row['error'] = error or 'invalid_internal_percentage'
        return row
    for key in ['battery_percent', 'cached_report_percent', 'sensor_average_raw']:
        row[key] = reading.get(key)
    standard, error = read_json([str(ROOT / 'build/keychron-raw-battery')])
    if error or not standard or not percent(standard.get('raw_battery_percent')):
        row.update(status='partial', error=error or 'invalid_standard_percentage')
    else:
        row.update(status='ok', standard_report_percent=standard['raw_battery_percent'])
    return row


def summarize(rows, metadata, finished=False, reason=None):
    good = [r for r in rows if percent(r.get('battery_percent'))]
    standard = [r['standard_report_percent'] for r in rows
                if percent(r.get('standard_report_percent'))]
    result = {'finished': finished, 'reason': reason, 'sample_count': len(rows),
              'valid_internal_samples': len(good),
              'planned_duration_seconds': metadata['duration_seconds'],
              'all_standard_values': sorted(set(standard)),
              'settings': metadata['settings'], 'last_sample': rows[-1] if rows else None}
    if good:
        result.update(first_internal_percent=good[0]['battery_percent'],
                      last_internal_percent=good[-1]['battery_percent'],
                      change_percentage_points=good[-1]['battery_percent'] - good[0]['battery_percent'],
                      observed_span_seconds=round(good[-1]['elapsed_seconds'] - good[0]['elapsed_seconds'], 2),
                      max_gap_seconds=round(max((b['elapsed_seconds'] - a['elapsed_seconds']
                                               for a, b in zip(good, good[1:])), default=0), 2))
    return result


def save_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration-seconds', type=int, default=3600)
    parser.add_argument('--interval-seconds', type=int, default=300)
    parser.add_argument('--color', default='white')
    parser.add_argument('--brightness', default='maximum')
    parser.add_argument('--power-state', choices=['discharging', 'charging'], default='discharging')
    args = parser.parse_args()
    if not (60 <= args.duration_seconds <= 7200 and 60 <= args.interval_seconds <= 900):
        parser.error('Duration must be 60-7200 seconds; sampling interval 60-900 seconds.')
    os.umask(0o077)
    base = ROOT / 'private/discharge-tests'
    base.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock = (base / 'logger.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A discharge logger is already running.')
    start = time.time()
    end = start + args.duration_seconds
    folder = base / (dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + f'-{os.getpid()}')
    folder.mkdir(mode=0o700)
    metadata = {'pid': os.getpid(), 'started_at_utc': dt.datetime.fromtimestamp(start, UTC).isoformat(),
                'ends_at_utc': dt.datetime.fromtimestamp(end, UTC).isoformat(),
                'duration_seconds': args.duration_seconds, 'interval_seconds': args.interval_seconds,
                'settings': {'backlight_color': args.color, 'brightness': args.brightness,
                             'charging': ('connected to charger; confirmed by owner' if args.power_state == 'charging'
                                          else 'previously unplugged; assumed unchanged'),
                             'auto_sleep': 'previously disabled; not changed by logger'},
                'notes': 'Battery estimate and raw sensor average; not a current/capacity measurement. '
                         'Sampling adds diagnostic traffic. No keyboard settings changed.',
                'folder': str(folder)}
    save_json(folder / 'metadata.json', metadata)
    save_json(base / 'active.json', metadata)
    rows, failures, next_due = [], 0, start
    try:
        with (folder / 'samples.jsonl').open('a', buffering=1) as log, \
                (folder / 'samples.csv').open('w', newline='') as table:
            writer = None
            while True:
                time.sleep(max(0, next_due - time.time()))
                final_sample = next_due >= end
                row = collect(start)
                rows.append(row)
                log.write(json.dumps(row) + '\n')
                if writer is None:
                    writer = csv.DictWriter(table, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                table.flush()
                failures = failures + 1 if row['battery_percent'] is None else 0
                reason = ('initial_read_failed' if len(rows) == 1 and failures else
                          'three_consecutive_read_failures' if failures >= 3 else
                          'duration_complete' if final_sample else None)
                summary = summarize(rows, metadata, bool(reason), reason)
                save_json(folder / 'summary.json', summary)
                print(json.dumps(row), flush=True)
                if reason:
                    return 0 if reason == 'duration_complete' else 1
                elapsed = time.time() - start
                # Skip missed intervals after host sleep; do not issue a burst of reads.
                next_due = min(end, start + (math.floor(elapsed / args.interval_seconds) + 1) * args.interval_seconds)
    except KeyboardInterrupt:
        save_json(folder / 'summary.json', summarize(rows, metadata, True, 'stopped_by_operator'))
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
