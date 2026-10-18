"""Account handoff outcomes, using the shipped TS decision and private IO store.

Synthetic native transport isolates model/network/auth effects. Installed native
transaction qualification is a separate opt-in drill, never a live-account test.
"""
import importlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Native slot effects use the POSIX account owner")


@pytest.fixture
def native(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "packages" /
                                   "loopx-codex-provider-routing" / "src"))
    module = importlib.import_module("loopx_codex_provider_routing.native")
    monkeypatch.setattr(module, "discover", lambda: {"synthetic": True})
    return module


class Clock:
    now = 1000

    def __call__(self):
        return self.now


class NativeTransport:
    def __init__(self, clock):
        self.clock = clock
        self.active = "a"
        self.revision = "initial"
        self.calls = []
        self.busy = False
        self.pending = False
        self.bad_quota = False
        self.committed_without_reply = False
        self.entered = self.release = None

    def __call__(self, adapter, operation, **parameters):
        from loopx_codex_provider_routing.native_host import HostError

        self.calls.append((operation, parameters))
        if operation == "status":
            return {"slots": ["a", "b"], "active_slot": self.active, "selection_revision": self.revision,
                    "current_login_matches": True, "recovery_required": self.pending}
        if operation == "observe":
            if self.entered:
                self.entered.set()
                assert self.release.wait(10)
            assert parameters["expected_revision"] == self.revision
            return {"observations": [{"slot": slot, "status": "unavailable" if self.bad_quota else "ok",
                                      "observed_at": self.clock(), "usage": {
                                          "rate_limit": {"primary_window": {"used_percent": 100 if slot == "a" else 12,
                                                                              "reset_at": 8000}},
                                          "credits": {"has_credits": False},
                                      }} for slot in parameters["slots"]]}
        if operation == "switch":
            if parameters["expected_revision"] != self.revision:
                raise HostError("selection_changed")
            if self.busy:
                raise HostError("waiting_for_idle")
            self.active, self.revision = parameters["slot"], "selected"
            if self.committed_without_reply:
                raise HostError("native_unavailable")
            return self(adapter, "status") | {"launch_failed": False, "history_untouched": True}
        if operation in ("recover", "rollback"):
            assert parameters["expected_revision"] == self.revision
            self.pending = False
            return self(adapter, "status")
        raise AssertionError(operation)


def configured(native, tmp_path):
    clock = Clock()
    transport = NativeTransport(clock)
    provider = native.NativeAccounts(tmp_path, transport=transport, clock=clock)
    provider.configure(expected_revision=0, enabled=True, slots=["a", "b"])
    return provider, transport, clock


def test_default_off_has_no_native_effect_or_startup_observer(native, tmp_path):
    from loopx.presentation.codex_accounts_api import CodexAccountService

    assert not native.NativeAccounts(tmp_path).path.exists()
    service = CodexAccountService(tmp_path)
    assert service.watcher.thread is None
    assert not native.NativeAccounts(tmp_path).root.exists()
    service.close()


def test_exhaustion_selects_once_and_manual_retry_is_idempotent(native, tmp_path):
    provider, transport, clock = configured(native, tmp_path)
    result = provider.tick(manual_slot="b", expected_selection="initial", operation_id="once")
    assert result["active_slot"] == "b"
    assert result["action"] == "selected"
    assert provider.tick(manual_slot="b", expected_selection="initial", operation_id="once")["active_slot"] == "b"
    assert len([call for call in transport.calls if call[0] == "switch"]) == 1
    assert provider.path.stat().st_mode & 0o077 == 0
    assert "access_token" not in json.dumps(result)
    clock.now += 301
    assert provider.tick()["action"] == "ready"


def test_unknown_quota_is_not_exhaustion(native, tmp_path):
    provider, transport, _ = configured(native, tmp_path)
    transport.bad_quota = True
    assert provider.tick()["action"] == "quota_unknown"
    assert not [call for call in transport.calls if call[0] == "switch"]


def test_busy_waits_then_switches_at_safe_boundary(native, tmp_path):
    provider, transport, clock = configured(native, tmp_path)
    transport.busy = True
    result = provider.tick()
    assert result["action"] == "waiting_for_idle" and result["active_slot"] == "a"
    assert json.loads(provider.path.read_text())["intent"]["target"] == "b"
    transport.busy = False
    clock.now += 61
    result = provider.tick()
    assert result["active_slot"] == "b" and result["action"] == "selected"
    assert all(call[0] not in ("kill", "terminate") for call in transport.calls)


def test_manual_native_selection_wins_over_queued_automatic_choice(native, tmp_path):
    provider, transport, clock = configured(native, tmp_path)
    transport.busy = True
    provider.tick()
    transport.revision = "external-choice"
    clock.now += 61
    before = len(transport.calls)
    assert provider.tick()["action"] == "selection_changed"
    assert all(call[0] != "switch" for call in transport.calls[before:])
    result = provider.tick(manual_slot="b", expected_selection="initial", operation_id="stale")
    assert result["action"] == "selection_changed"
    assert transport.active == "a"


def test_lost_reply_recovers_readback_without_replaying_switch(native, tmp_path):
    provider, transport, clock = configured(native, tmp_path)
    transport.committed_without_reply = True
    assert provider.tick()["action"] == "unavailable"
    restarted = native.NativeAccounts(tmp_path, transport=transport, clock=clock)
    result = restarted.tick(refresh=True)
    assert result["active_slot"] == "b" and result["action"] == "selected"
    assert len([call for call in transport.calls if call[0] == "switch"]) == 1


def test_recovery_stops_auto_and_preserves_revision_fence(native, tmp_path):
    provider, transport, _ = configured(native, tmp_path)
    transport.pending = True
    assert provider.tick()["action"] == "recovery_required"
    result = provider.recover(rollback=False, expected_revision=1, expected_selection="initial")
    assert result["policy"]["enabled"] is False
    assert not result["recovery_required"]
    with pytest.raises(Exception, match="configuration_changed"):
        provider.configure(expected_revision=1, enabled=True, slots=["a", "b"])


def test_two_hosts_cannot_switch_concurrently(native, tmp_path):
    provider, transport, clock = configured(native, tmp_path)
    transport.entered, transport.release = threading.Event(), threading.Event()
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(provider.tick()))
    thread.start()
    assert transport.entered.wait(5)
    contender = native.NativeAccounts(tmp_path, transport=transport, clock=clock)
    try:
        with pytest.raises(BlockingIOError):
            contender.tick()
    finally:
        transport.release.set()
        thread.join(10)
    assert outcome[0]["active_slot"] == "b"
    assert len([call for call in transport.calls if call[0] == "switch"]) == 1


def test_disable_and_stop_before_effect_preserve_login(native, tmp_path):
    provider, transport, _ = configured(native, tmp_path)
    provider.switch_allowed = lambda: False
    provider.tick()
    assert transport.active == "a"
    provider.configure(expected_revision=1, enabled=False, slots=["a", "b"])
    before = len(transport.calls)
    assert provider.tick()["action"] == "disabled"
    assert len(transport.calls) == before
    # Turning automatic effects off does not revoke an explicit manual choice.
    result = provider.tick(manual_slot="b", expected_selection="initial", operation_id="manual-after-disable")
    assert result["active_slot"] == "b" and result["policy"]["enabled"] is False


def test_first_explicit_check_does_not_enable_automatic_switches(native, tmp_path):
    clock = Clock()
    transport = NativeTransport(clock)
    provider = native.NativeAccounts(tmp_path, transport=transport, clock=clock)
    result = provider.tick(refresh=True)
    assert result["policy"]["enabled"] is False and result["accounts"]
    assert not [call for call in transport.calls if call[0] == "switch"]


def test_unknown_upstream_fields_do_not_reach_policy_or_persistence(native):
    from loopx_codex_provider_routing.native_host import quota_fields

    result = quota_fields({"access_token": "synthetic-only", "email": "person@example.invalid",
                           "rate_limit": {"primary_window": {"used_percent": 10, "secret": "synthetic-only"}},
                           "credits": {"has_credits": False, "refresh_token": "synthetic-only"}})
    assert "synthetic-only" not in json.dumps(result)
    assert result["rate_limit"]["primary_window"]["used_percent"] == 10


def test_rejected_inactive_login_is_not_repeatedly_refreshed(native, tmp_path, monkeypatch):
    from loopx_codex_provider_routing import native_host as module

    active, inactive = tmp_path / "active", tmp_path / "inactive"
    active.write_bytes(b"synthetic-active")
    inactive.write_bytes(b"synthetic-expired")
    adapter = module.NativeHost.__new__(module.NativeHost)
    adapter.manager = SimpleNamespace(auth=active, slot=lambda _: inactive)
    adapter.accounts = SimpleNamespace(read_private=lambda path: path.read_bytes())
    adapter.status = lambda: {"slots": ["a", "b"], "active_slot": "a",
                              "selection_revision": "stable", "recovery_required": False}
    calls = []

    def usage(raw):
        if raw == b"synthetic-active":
            return {}
        raise module.HostError("auth_required")

    def refresh(*args):
        calls.append(args)
        raise module.HostError("auth_required")

    monkeypatch.setattr(module, "read_usage", usage)
    adapter.refresh_inactive = refresh
    result = adapter.observe(["a", "b"], "stable")
    failed = result["observations"][1]
    cached = {"b": {"revision": failed["credential_revision"], "observed_at": failed["observed_at"]}}
    assert adapter.observe(["a", "b"], "stable", cached)["observations"][1] == failed
    assert len(calls) == 1
    inactive.write_bytes(b"synthetic-replaced-login")
    adapter.observe(["a", "b"], "stable", cached)
    assert len(calls) == 2


def test_source_pins_and_symlink_state_are_not_silently_adopted(native, tmp_path):
    from loopx_codex_provider_routing.native_host import NativeHost, HostError

    (tmp_path / "personal_apps.py").write_text("# synthetic owner\n")
    with pytest.raises(HostError, match="adapter_changed"):
        NativeHost({"source": str(tmp_path), "pins": {"personal_apps.py": "bad"}, "codex": "unused"})
    provider = native.NativeAccounts(tmp_path)
    provider.root.mkdir(parents=True)
    provider.path.symlink_to(tmp_path / "personal_apps.py")
    with pytest.raises(HostError, match="state_untrusted"):
        provider._load()


def test_http_adapter_rejects_secret_and_arbitrary_command_fields(native, tmp_path):
    from loopx.presentation.codex_accounts_api import CodexAccountsRequestMixin

    class Handler(CodexAccountsRequestMixin):
        def _read_json(self):
            return {"operation": "configure", "parameters": {"access_token": "synthetic-only"}}

        def _send_json(self, payload, *, status=200):
            self.sent, self.code = payload, status

    handler = Handler()
    handler._codex_accounts_write()
    assert handler.code == 409 and handler.sent["code"] == "invalid_request"
    assert "synthetic-only" not in json.dumps(handler.sent)
