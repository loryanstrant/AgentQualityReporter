"""Rule catalogue parsing tests."""
from engine.loader import load_rules


def test_catalogue_loads_expected_rules():
    rules = load_rules()
    ids = {r["id"] for r in rules}
    for rid in ("SOL-001", "CON-001", "ENV-001", "AGT-001", "AGT-009"):
        assert rid in ids
    # AGT-010/011 (auth/publish) were dropped — not grounded in the P&P deck.
    assert "AGT-010" not in ids
    assert "AGT-011" not in ids


def test_every_rule_has_metadata():
    for r in load_rules():
        assert r["name"]
        assert r["severity"] in {"blocker", "major", "minor", "info"}
        assert r["pp_reference"]
