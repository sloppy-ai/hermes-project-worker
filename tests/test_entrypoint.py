import runpy

import pytest


def test_package_entrypoint_delegates_to_cli_main(monkeypatch):
    calls = []

    def fake_main(argv=None):
        calls.append(argv)
        return 7

    monkeypatch.setattr("hermes_project_worker.cli.main", fake_main)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("hermes_project_worker", run_name="__main__")

    assert exc.value.code == 7
    assert calls == [None]
