"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _metric_map(spec: dict) -> dict[str, dict]:
    return {m["id"]: m for m in spec.get("metrics", [])}


def _is_nan_or_inf(v) -> bool:
    return isinstance(v, float) and not math.isfinite(v)


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
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    for mid, val in (pr.get("metrics") or {}).items():
        if _is_nan_or_inf(val):
            problems.append(f"metric {mid} is {val} -- a crashed/edited number, not a measurement")

    manifest = pr.get("manifest") or {}
    want = int(manifest.get("items") or 0) * len(manifest.get("seeds") or [])
    rows = pr.get("rows") or []
    if len(rows) != want:
        problems.append(f"rows={len(rows)} but manifest says {manifest.get('items')}x{len(manifest.get('seeds') or [])}={want}")

    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    for r in rows:
        missing = [mid for mid in graded if r.get(mid) is None]
        if missing:
            problems.append(f"{r.get('item_id')}@{r.get('seed')}: graded metric(s) {','.join(missing)} are None (dropped from every mean)")

    pr_cells = {(r.get("item_id"), r.get("seed")) for r in rows}
    base_cells = {(r.get("item_id"), r.get("seed")) for r in (base.get("rows") or [])}
    if base_cells and pr_cells != base_cells:
        problems.append(f"(item, seed) set differs from baseline: {len(pr_cells - base_cells)} missing, "
                        f"{len(base_cells - pr_cells)} extra")

    pr_slices: dict[str, set] = {}
    for r in rows:
        pr_slices.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
    base_slices: dict[str, set] = {}
    for r in base.get("rows") or []:
        base_slices.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
    for item_id in sorted(set(pr_slices) & set(base_slices)):
        if pr_slices[item_id] != base_slices[item_id]:
            problems.append(f"{item_id}: slice tags changed from {sorted(base_slices[item_id])} to {sorted(pr_slices[item_id])}")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_m = _metric_map(base_spec)
        for mid, bm in base_m.items():
            sm = _metric_map(spec).get(mid)
            if sm is None:
                problems.append(f"metric {mid} disappeared from the spec")
                continue
            if bool(bm.get("blocking")) and not bool(sm.get("blocking")):
                problems.append(f"metric {mid} went from blocking to non-blocking")
            bt, st = bm.get("threshold") or {}, sm.get("threshold") or {}
            if "max" in bt and ("max" not in st or st["max"] > bt["max"]):
                problems.append(f"metric {mid}: max {bt['max']} loosened to {st.get('max')}")
            if "min" in bt and ("min" not in st or st["min"] < bt["min"]):
                problems.append(f"metric {mid}: min {bt['min']} loosened to {st.get('min')}")
            if "max_increase" in bt and ("max_increase" not in st or st["max_increase"] > bt["max_increase"]):
                problems.append(f"metric {mid}: max_increase {bt['max_increase']} loosened to {st.get('max_increase')}")
            if bt.get("no_significant_drop") and not st.get("no_significant_drop"):
                problems.append(f"metric {mid}: no_significant_drop dropped")
        spec_slices = {s.get("name"): s for s in spec.get("slices") or []}
        for bs in base_spec.get("slices") or []:
            name = bs.get("name")
            ss = spec_slices.get(name)
            if ss is None:
                problems.append(f"slice {name} disappeared from the spec")
                continue
            if ss.get("metric") != bs.get("metric"):
                problems.append(f"slice {name}: metric changed {bs.get('metric')} -> {ss.get('metric')}")
            if "min" in bs and ("min" not in ss or ss["min"] < bs["min"]):
                problems.append(f"slice {name}: min {bs['min']} loosened to {ss.get('min')}")
            if bs.get("no_significant_drop") and not ss.get("no_significant_drop"):
                problems.append(f"slice {name}: no_significant_drop dropped")
            if bool(bs.get("blocking")) and not bool(ss.get("blocking")):
                problems.append(f"slice {name}: went from blocking to non-blocking")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        sid = f"slice:{name}/{mid}"
        per = per_item(pr, mid, slice_name=name)
        base_per = per_item(base, mid, slice_name=name)
        val = round(sum(per.values()) / len(per), 4) if per else None
        note, verdict = "", "ok"
        th = s.get("threshold") or s
        if val is None:
            verdict = "missing"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
            note = f"< min {th['min']}"
        if s.get("no_significant_drop") and per and base_per:
            keys = sorted(set(per) & set(base_per))
            d, lo, hi = stats.paired_bootstrap([per[k] for k in keys], [base_per[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = (note + " " if note else "") + f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        lines.append(f"  {sid:<34} {val!s:<8} {note:<28} {label}")
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
