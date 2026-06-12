import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "maildrop-public-smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("maildrop_public_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_smoke_skips_when_production_check_is_not_ready(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(module, "run_production_check", lambda _target: 2)

    result = module.run_smoke(
        module.SmokeTarget("aiprot.space", "emailengine", "167.71.29.22"),
        timeout_seconds=1,
        poll_seconds=1,
    )

    assert result == 2
    assert "DNS_OR_SERVICE_NOT_READY" in capsys.readouterr().out


def test_public_smoke_sends_message_and_waits_for_database_confirmation(monkeypatch):
    module = load_module()
    sent = {}

    monkeypatch.setattr(module, "run_production_check", lambda _target: 0)
    monkeypatch.setattr(module.secrets, "token_hex", lambda _size: "abcd1234")
    monkeypatch.setattr(module.time, "time", lambda: 1781208000)

    def fake_send(domain, recipient, subject, body):
        sent["domain"] = domain
        sent["recipient"] = recipient
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(module, "send_public_smtp", fake_send)
    monkeypatch.setattr(
        module,
        "latest_unassigned_subject",
        lambda _server_host, _recipient: sent["subject"],
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.run_smoke(
        module.SmokeTarget("aiprot.space", "emailengine", "167.71.29.22"),
        timeout_seconds=1,
        poll_seconds=1,
    )

    assert result == 0
    assert sent["domain"] == "aiprot.space"
    assert sent["recipient"] == "public-smoke-1781208000-abcd1234@aiprot.space"
    assert sent["subject"] == "Public Smoke 1781208000-abcd1234"
    assert "Public SMTP smoke body" in sent["body"]


def test_public_smoke_falls_back_to_server_side_smtp_when_local_send_times_out(monkeypatch):
    module = load_module()
    sent = {}

    monkeypatch.setattr(module, "run_production_check", lambda _target: 0)
    monkeypatch.setattr(module.secrets, "token_hex", lambda _size: "abcd1234")
    monkeypatch.setattr(module.time, "time", lambda: 1781208000)

    def fake_public_send(_domain, _recipient, _subject, _body):
        raise TimeoutError("local outbound smtp blocked")

    def fake_server_send(server_host, domain, recipient, subject, body):
        sent["server_host"] = server_host
        sent["domain"] = domain
        sent["recipient"] = recipient
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(module, "send_public_smtp", fake_public_send)
    monkeypatch.setattr(module, "send_server_smtp", fake_server_send)
    monkeypatch.setattr(
        module,
        "latest_unassigned_subject",
        lambda _server_host, _recipient: sent["subject"],
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.run_smoke(
        module.SmokeTarget("aiprot.space", "emailengine", "167.71.29.22"),
        timeout_seconds=1,
        poll_seconds=1,
    )

    assert result == 0
    assert sent["server_host"] == "emailengine"
    assert sent["domain"] == "aiprot.space"
    assert sent["recipient"] == "public-smoke-1781208000-abcd1234@aiprot.space"


def test_latest_unassigned_subject_queries_server_with_safe_recipient(monkeypatch):
    module = load_module()
    calls = []

    def fake_run(args, text, capture_output, check):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="Subject\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    subject = module.latest_unassigned_subject(
        "emailengine",
        "public-smoke@example.test",
    )

    assert subject == "Subject"
    assert calls[0][0] == "ssh"
    assert calls[0][1] == "emailengine"
    assert "unassigned_messages" in calls[0][2]
