"""Anthropic-API-Schlüssel: geschützt abgelegt (wie das ITM-Token), alter Klartext wird übernommen."""
import os

import pytest


@pytest.fixture
def local_dir(tmp_path, monkeypatch):
    import ai_classifier as ai
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai.storage, "local_dir", lambda: str(tmp_path))
    return tmp_path


def _stored(folder):
    with open(os.path.join(folder, "anthropic_key.txt"), encoding="utf-8") as f:
        return f.read()


def test_schluessel_nicht_im_klartext(local_dir):
    import ai_classifier as ai
    ai.save_api_key("  sk-ant-test-123  ")
    assert "sk-ant-test-123" not in _stored(local_dir)
    assert ai.api_key() == "sk-ant-test-123"


def test_alter_klartext_wird_gelesen_und_geschuetzt(local_dir):
    import ai_classifier as ai
    with open(os.path.join(local_dir, "anthropic_key.txt"), "w", encoding="utf-8") as f:
        f.write("sk-ant-alt-456\n")
    assert ai.api_key() == "sk-ant-alt-456"
    assert "sk-ant-alt-456" not in _stored(local_dir)
    assert ai.api_key() == "sk-ant-alt-456"


def test_leer_loescht_die_datei(local_dir):
    import ai_classifier as ai
    ai.save_api_key("sk-ant-x")
    ai.save_api_key("")
    assert not os.path.exists(os.path.join(local_dir, "anthropic_key.txt"))
    assert ai.api_key() == ""
