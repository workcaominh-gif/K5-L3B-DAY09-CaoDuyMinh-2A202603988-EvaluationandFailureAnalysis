"""Regression test from docs/trace_case.md: seeded_regression C-008@11 (FM-08 misreport).

The Lab 8 grader PASSES this trial (ledger 20.000 = label), but the reply tells the customer
35.000. Only ReplyMatchesLedger catches it. The test re-runs the real shapes on a temp store
and does not depend on any optional trace event (e.g. host_outcome).
"""
import pytest

pytestmark = pytest.mark.student


def _trial(shape, claim="C-008", seed=11):
    from lab9.trace_case import investigate

    case = investigate(shape, claim, seed)
    return case["trial"], case["label"]


def _reply_ok(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyMatchesLedger

    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return ReplyMatchesLedger().evaluate(ctx)


def test_lab9_trace_case_misreport_caught_on_seeded_regression():
    trial, label = _trial("seeded_regression")
    assert trial["lab8_pass"] is True                       # Lab 8 grader alone misses it
    assert trial["snapshot"]["refund_vnd"] == label["refund_vnd"] == 20000
    res = _reply_ok(trial, label)
    assert res.value is False and "35000" in res.reason      # reply says 35.000, ledger holds 20.000


def test_lab9_trace_case_reply_matches_ledger_on_fixed():
    trial, label = _trial("fixed")
    assert trial["lab8_pass"] is True
    assert _reply_ok(trial, label).value is True
