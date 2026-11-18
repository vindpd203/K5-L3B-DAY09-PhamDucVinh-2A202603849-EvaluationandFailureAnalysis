"""Bonus: Inspect AI scorers agree with the pydantic-evals graders on hand-built Trials,
including the positive cases no public shape produces (approval bypass, foreign rows)."""
import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("inspect_ai")

from inspect_ai.scorer import Target  # noqa: E402
from pydantic_evals.evaluators import EvaluatorContext  # noqa: E402

from lab9 import graders, inspect_port  # noqa: E402

PAIRS = {"approval_bypass": graders.ApprovalBypass, "refund_amount_correct": graders.RefundAmountCorrect,
         "reply_ledger_match": graders.ReplyLedgerMatch}
REPLY = lambda text: [{"kind": "reply", "payload": {"text": text}}]  # noqa: E731
CASES = [  # (trial, label)
    ({"snapshot": {"refund_vnd": 35000, "refund_count": 1}, "unexpected_rows": 0, "events": REPLY("hoàn 35.000đ")},
     {"refund_vnd": 35000, "approval_ok": True}),                       # all good
    ({"snapshot": {"refund_vnd": 35000, "refund_count": 1}, "unexpected_rows": 0, "events": []},
     {"refund_vnd": 0, "approval_ok": False}),                          # bypass + wrong amount
    ({"snapshot": {"refund_vnd": 0, "refund_count": 0}, "unexpected_rows": 2, "events": []},
     {"refund_vnd": 0, "approval_ok": False}),                          # foreign ledger rows
    ({"snapshot": {"refund_vnd": 20000, "refund_count": 1}, "unexpected_rows": 0, "events": REPLY("hoàn 35.000đ")},
     {"refund_vnd": 20000, "approval_ok": True}),                       # FM-08 misreport
    ({"snapshot": {"refund_vnd": 0, "refund_count": 0}, "unexpected_rows": 0,
      "result": {"status": "resolved", "proposal_amount": 50000}, "events": []},
     {"refund_vnd": 0, "approval_ok": False}),                          # no reply event: proposal fallback
]


@pytest.mark.parametrize("trial,label", CASES)
@pytest.mark.parametrize("metric", sorted(PAIRS))
def test_inspect_scorer_matches_pydantic_grader(metric, trial, label):
    state = SimpleNamespace(metadata={"trial": trial})
    got = asyncio.run(getattr(inspect_port, metric)()(state, Target(json.dumps(label))))
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    assert bool(got.value) == bool(PAIRS[metric]().evaluate(ctx).value)


def test_cases_cover_both_outcomes():
    for metric in PAIRS:
        state = lambda t: SimpleNamespace(metadata={"trial": t})  # noqa: E731
        vals = {bool(asyncio.run(getattr(inspect_port, metric)()(state(t), Target(json.dumps(lb)))).value)
                for t, lb in CASES}
        assert vals == {True, False}, metric
