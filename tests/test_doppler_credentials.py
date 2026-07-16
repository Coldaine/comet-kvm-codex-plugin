from __future__ import annotations

import pytest

from src.kvm_core import doppler_credentials as dc


class SecretTranscript:
    """Recorded Doppler secret results with an auditable lookup order."""

    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.names: list[str] = []

    def __call__(self, name: str, project: str, config: str) -> str | None:
        assert (project, config) == ("homelab", "dev")
        self.names.append(name)
        return self.values.get(name)


def test_password_selection_uses_canonical_doppler_secret_first(monkeypatch):
    monkeypatch.setenv("COMET_PASSWORD", "env-must-be-ignored")
    monkeypatch.setenv("GLCOMET_ADMIN_PASSWORD", "also-ignored")
    transcript = SecretTranscript({"GLCOMET_ADMIN_PASSWORD": "from-doppler"})

    password = dc._resolve_password_from_reader(
        transcript,
        "homelab",
        "dev",
        require=True,
    )

    assert password == "from-doppler"
    assert transcript.names == ["GLCOMET_ADMIN_PASSWORD"]


def test_resolve_comet_password_raises_when_doppler_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(dc.DopplerAuthError, match="Doppler CLI not found"):
        dc.resolve_comet_password(require=True)
