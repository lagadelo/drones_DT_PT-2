#!/usr/bin/env python3
"""List the timeline of loss and spare-insertion events.

Reads:
- losses CSV: step,idx (comma or semicolon)
- trace CSV from baseline_simulator: step;idx;alive;...

Outputs:
1) merged chronological event list (LOSS / SPARE) with delta to previous event
2) for each LOSS, the next SPARE after it and the delay

Example:
  python3 Code/list_loss_spare_timeline.py \
    --losses Code/losses_seeded.csv \
    --trace Code/trace_w05_seed.csv \
    --dt 0.1
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Event:
    step: int
    kind: str  # "LOSS" or "SPARE"
    detail: str


def read_loss_events(path: Path) -> list[Event]:
    if not path.exists():
        raise FileNotFoundError(path)
    events: list[Event] = []
    with path.open() as f:
        header = f.readline()
        delim = ";" if ";" in header else ","
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.replace(";", ",").split(",")
            if len(parts) < 2:
                continue
            try:
                step = int(parts[0])
                idx = int(parts[1])
            except ValueError:
                continue
            events.append(Event(step=step, kind="LOSS", detail=f"idx={idx}"))
    events.sort(key=lambda e: e.step)
    return events


def read_spare_events_from_trace(path: Path) -> list[Event]:
    if not path.exists():
        raise FileNotFoundError(path)
    prev_alive: dict[int, int] = {}
    events: list[Event] = []
    with path.open() as f:
        f.readline()  # header
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 3:
                continue
            try:
                step = int(parts[0])
                idx = int(parts[1])
                alive = int(parts[2])
            except ValueError:
                continue
            prev = prev_alive.get(idx)
            if prev is not None and prev == 0 and alive == 1:
                events.append(Event(step=step, kind="SPARE", detail=f"idx={idx}"))
            prev_alive[idx] = alive
    events.sort(key=lambda e: e.step)
    return events


def fmt_time(step: int, dt: float | None) -> str:
    if dt is None:
        return ""
    return f" ({step * dt:.3f}s)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--losses", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--dt", type=float, default=None, help="seconds per step (optional)")
    args = ap.parse_args()

    losses = read_loss_events(args.losses)
    spares = read_spare_events_from_trace(args.trace)

    merged = sorted([*losses, *spares], key=lambda e: (e.step, 0 if e.kind == "LOSS" else 1))

    print("loss_file", args.losses)
    print("trace_file", args.trace)
    if args.dt is not None:
        print("dt", args.dt)
    print()

    print("# 1) Chronological event list")
    prev_step: int | None = None
    for e in merged:
        delta = ""
        if prev_step is not None:
            delta = f"  +{e.step - prev_step}"
            if args.dt is not None:
                delta += f" steps (+{(e.step - prev_step) * args.dt:.3f}s)"
        t = fmt_time(e.step, args.dt)
        print(f"{e.step:5d}{t}  {e.kind:5s}  {e.detail}{delta}")
        prev_step = e.step

    print()
    print("# 2) For each LOSS, next SPARE and delay")
    spare_steps = [e.step for e in spares]
    j = 0
    for loss in losses:
        while j < len(spare_steps) and spare_steps[j] <= loss.step:
            j += 1
        next_spare = spare_steps[j] if j < len(spare_steps) else None
        if next_spare is None:
            print(f"LOSS {loss.step:5d}{fmt_time(loss.step, args.dt)} -> next SPARE: none")
        else:
            delay = next_spare - loss.step
            delay_s = f" ({delay * args.dt:.3f}s)" if args.dt is not None else ""
            print(
                f"LOSS {loss.step:5d}{fmt_time(loss.step, args.dt)} -> SPARE {next_spare:5d}{fmt_time(next_spare, args.dt)}  delay {delay}{delay_s}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
