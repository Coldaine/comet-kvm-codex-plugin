from __future__ import annotations

from unittest.mock import patch

import pytest

from src.kvm_core import doppler_credentials as dc


def test_resolve_comet_password_uses_doppler_not_env(monkeypatch):
    monkeypatch.setenv("COMET_PASSWORD", "env-must-be-ignored")
    monkeypatch.setenv("GLCOMET_ADMIN_PASSWORD", "also-ignored")

    with patch.object(dc, "assert_doppler_authenticated"):
        with patch.object(dc, "_doppler_get_plain", side_effect=["from-doppler", None]) as get_plain:
            password = dc.resolve_comet_password(require=True)

    assert password == "from-doppler"
    assert get_plain.call_args_list[0].args[0] == "COMET_PASSWORD"


def test_resolve_comet_password_raises_when_doppler_unauthenticated():
    with patch.object(dc, "doppler_cli_available", return_value=False):
        with pytest.raises(dc.DopplerAuthError, match="Doppler CLI not found"):
            dc.resolve_comet_password(require=True)
