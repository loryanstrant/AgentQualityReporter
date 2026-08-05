"""Per-agent scoring behaviour on the demo environment."""
from engine.demo import demo_environment
from engine.loader import load_model_config, load_rules
from engine.static_rules import run_static_rules


def _score_agent(agent):
    rules = load_rules()
    mc = load_model_config()
    parsed = {
        "source": "demo",
        "solution": agent["solution"],
        "connection_references": agent["connection_references"],
        "environment_variables": agent["environment_variables"],
        "bots": [agent],
    }
    return run_static_rules(
        parsed, rules, icon_config={"known_default_hashes": []}, model_config=mc.get("model", {})
    )


def _agents():
    return {a["display_name"]: a for a in demo_environment()["agents"]}


def test_good_agent_scores_A():
    res = _score_agent(_agents()["Contoso HR Assistant"])
    assert res.score == 100
    assert res.grade == "A"


def test_poor_agent_scores_C():
    res = _score_agent(_agents()["Test Bot"])
    # AGT-007 (App Insights) is manual-review, so the poor agent no longer loses
    # those points on a Dataverse-only scan; it lands at 61 (grade C).
    assert res.score == 61
    assert res.grade == "C"


def test_default_solution_agent_fails_sol001():
    res = _score_agent(_agents()["Test Bot"])
    by = {f.rule_id: f for f in res.findings}
    assert by["SOL-001"].status == "fail"  # only in the default solution


def test_custom_icon_scoring():
    good = {f.rule_id: f for f in _score_agent(_agents()["Contoso HR Assistant"]).findings}
    poor = {f.rule_id: f for f in _score_agent(_agents()["Test Bot"]).findings}
    assert good["AGT-009"].status == "pass"   # custom icon
    assert poor["AGT-009"].status == "fail"   # default icon shared across agents


def test_description_scored_live():
    poor = {f.rule_id: f for f in _score_agent(_agents()["Test Bot"]).findings}
    # AGT-002 (description) IS live-scored from Dataverse.
    assert poor["AGT-002"].status == "fail"
    assert poor["AGT-002"].manual_review is False


def test_appinsights_is_manual_review_without_telemetry():
    # App Insights config isn't exposed via Dataverse, so AGT-007 must never fail
    # on absence — it's manual review unless telemetry is observed.
    poor = {f.rule_id: f for f in _score_agent(_agents()["Test Bot"]).findings}
    assert poor["AGT-007"].status == "skipped"
    assert poor["AGT-007"].manual_review is True
    assert poor["AGT-007"].weight == 0


def test_appinsights_passes_when_telemetry_observed():
    # The good demo agent has observed telemetry (run_count set) -> PASS.
    good = {f.rule_id: f for f in _score_agent(_agents()["Contoso HR Assistant"]).findings}
    assert good["AGT-007"].status == "pass"
