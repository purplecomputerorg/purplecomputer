"""A change to how Purple Packs are written or read is a decision, not drift: scripts/pack_contract.py."""

from scripts.pack_contract import problems


def test_pack_contract_is_decided():
    assert not problems(), "\n\n".join(problems())
