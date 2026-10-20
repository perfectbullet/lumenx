"""Provider authentication changes must take effect without restarting the app."""

from unittest.mock import Mock

import pytest

from src.models import mulerouter
from src.apps.playground.models import GenerateRequest
from src.apps.playground.service import PlaygroundService


def test_cli_login_after_failed_detection_is_used(monkeypatch):
    monkeypatch.delenv("MULEROUTER_API_KEY", raising=False)
    check = Mock(side_effect=[False, True, False])
    monkeypatch.setattr(mulerouter, "_is_mulerun_cli_available", check)

    assert mulerouter._use_cli_backend() is False
    assert mulerouter._use_cli_backend() is True
    assert mulerouter._use_cli_backend() is False


def test_api_key_takes_priority_over_cli(monkeypatch):
    monkeypatch.setenv("MULEROUTER_API_KEY", "test-key")
    check = Mock()
    monkeypatch.setattr(mulerouter, "_is_mulerun_cli_available", check)
    assert mulerouter._use_cli_backend() is False
    check.assert_not_called()


def test_missing_auth_explains_how_to_configure(monkeypatch):
    monkeypatch.delenv("MULEROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Settings.*MuleRouter.*MULEROUTER_API_KEY.*MuleRun"):
        mulerouter._get_api_key()


def test_missing_auth_is_reported_as_failed_generation(monkeypatch, tmp_path):
    monkeypatch.delenv("MULEROUTER_API_KEY", raising=False)
    monkeypatch.setattr(mulerouter, "_is_mulerun_cli_available", lambda: False)
    monkeypatch.setattr("src.apps.playground.service.IMAGE_OUTPUT_DIR", str(tmp_path))
    storage = Mock()
    service = PlaygroundService(storage)
    gen = service.create_generation(GenerateRequest(
        mode="t2i", model_id="gpt-image-2", prompt="test",
    ))
    storage.get_generation.return_value = gen
    service.process_generation(gen.id)

    assert gen.status == "failed"
    assert "MULEROUTER_API_KEY" in gen.error
    assert "Settings" in gen.error
    assert gen.outputs == []
    assert storage.update_generation.call_args.args[0].status == "failed"
