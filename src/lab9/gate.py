"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    import math

    from lab9.graders import GRADERS

    problems: list[str] = []
    for side, rep in (("PR", pr), ("baseline", base)):
        for k, v in (rep.get("metrics") or {}).items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                problems.append(f"{side} metric {k} is {v} (a crashed grader hidden as NaN/inf)")

    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man = pr.get("manifest") or {}
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"PR has {len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"PR has {len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        missing, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra"
                        " (dropped rows or cherry-picked seeds/items)")
    if spec.get("seeds") and sorted(man.get("seeds") or []) != sorted(spec["seeds"]):
        problems.append(f"PR seeds {man.get('seeds')} != spec seeds {spec['seeds']}")
    if base_rows and sorted({s for _, s in base_keys}) != sorted({s for _, s in keys}):
        problems.append("PR seed set differs from the baseline's")

    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in PR")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for m in graded:
        if base_rows and not any(m in r for r in base_rows):
            continue                                    # metric not graded on either side
        none_rows = sum(1 for r in rows if r.get(m) is None)
        if none_rows:
            problems.append(f"{none_rows} PR row(s) have no value for graded metric {m} (grader crash dropped from the mean)")
        # The reported number must be what the rows say (a hand-edited headline is not a measurement).
        vals = [r[m] for r in rows if r.get(m) is not None]
        rep_v = (pr.get("metrics") or {}).get(m)
        if vals and isinstance(rep_v, (int, float)) and not (isinstance(rep_v, float) and math.isnan(rep_v)):
            calc = sum(vals) if m in ("secret_leak", "approval_bypass") else sum(vals) / len(vals)
            if abs(calc - rep_v) > 1e-3:
                problems.append(f"PR metric {m}={rep_v} does not match its rows ({calc:.4f})")

    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    for r in rows:
        b = base_slices.get(r.get("item_id"))
        if b is not None and sorted(r.get("slices") or []) != b:
            problems.append(f"{r.get('item_id')}: slice tags {sorted(r.get('slices') or [])} differ from baseline {b}")
            break

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: thresholds may only get stricter, nothing may disappear."""
    out: list[str] = []

    def cmp(where: str, new: dict | None, old: dict) -> None:
        if new is None:
            out.append(f"ratchet: {where} removed")
            return
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"ratchet: {where} no longer blocking")
        nt = new.get("threshold", new) if "threshold" in old else new
        ot = old.get("threshold", old)
        for k in ("max", "max_increase"):
            if k in ot and (k not in nt or nt[k] > ot[k]):
                out.append(f"ratchet: {where} {k} loosened {ot[k]} -> {nt.get(k)}")
        if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
            out.append(f"ratchet: {where} min loosened {ot['min']} -> {nt.get('min')}")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"ratchet: {where} dropped no_significant_drop")

    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        cmp(f"metric {m['id']}", new_m.get(m["id"]), m)
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        cmp(f"slice {s['name']}/{s['metric']}", new_s.get((s["name"], s["metric"])), s)
    if spec.get("seeds") is not None and base_spec.get("seeds") is not None \
            and sorted(spec["seeds"]) != sorted(base_spec["seeds"]):
        out.append("ratchet: seed set changed on the same eval-set version")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            verdict, val = "fail", None            # an empty slice cannot vouch for anything
            note = "no items in slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
