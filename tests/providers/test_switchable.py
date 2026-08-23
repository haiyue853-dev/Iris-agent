import threading

from iris_agent.core.models import ProviderResponse
from iris_agent.providers import switchable
from iris_agent.providers.switchable import SwitchableProvider


class Provider:
    def __init__(self, text): self.text = text; self.closed = 0
    def complete(self, messages, tools): return ProviderResponse(content=self.text)
    def stream(self, messages, tools): yield ProviderResponse(content=self.text)
    def close(self): self.closed += 1


def test_replace_closes_idle_old_provider_but_not_new_provider():
    old, new = Provider("old"), Provider("new")
    handle = SwitchableProvider(old)
    handle.replace(new)
    assert old.closed == 1
    assert new.closed == 0
    assert handle.current() is new


def test_replace_defers_close_until_active_lease_finishes():
    old, new = Provider("old"), Provider("new")
    handle = SwitchableProvider(old)
    with handle.lease() as leased:
        assert leased is old
        handle.replace(new)
        assert old.closed == 0
    assert old.closed == 1
    assert new.closed == 0


def test_stream_holds_lease_until_generator_is_closed():
    entered, release = threading.Event(), threading.Event()
    class Blocking(Provider):
        def stream(self, messages, tools):
            entered.set(); release.wait(1); yield ProviderResponse(content=self.text)
    old, new = Blocking("old"), Provider("new")
    handle = SwitchableProvider(old)
    stream = handle.stream([], [])
    worker = threading.Thread(target=lambda: next(stream))
    worker.start(); assert entered.wait(1)
    handle.replace(new)
    assert old.closed == 0
    release.set(); worker.join(1); stream.close()
    assert old.closed == 1


def test_close_is_idempotent():
    provider = Provider("one")
    handle = SwitchableProvider(provider)
    handle.close(); handle.close()
    assert provider.closed == 1


def test_reused_provider_identity_does_not_skip_closing_new_generation(monkeypatch):
    monkeypatch.setattr(switchable, "id", lambda provider: 42, raising=False)
    old, new = Provider("old"), Provider("new")
    handle = SwitchableProvider(old)

    handle.replace(new)
    handle.close()

    assert old.closed == 1
    assert new.closed == 1


def test_retired_leased_provider_can_be_restored_without_old_lease_closing_it():
    first, second, third = Provider("first"), Provider("second"), Provider("third")
    handle = SwitchableProvider(first)

    with handle.lease() as leased:
        assert leased is first
        handle.replace(second)
        handle.replace(first)
        assert second.closed == 1
        assert first.closed == 0
        assert handle.current() is first

    assert first.closed == 0
    handle.replace(third)
    assert first.closed == 1
    assert third.closed == 0


def test_replace_current_provider_with_same_object_is_noop():
    provider = Provider("same")
    handle = SwitchableProvider(provider)

    handle.replace(provider)

    assert handle.current() is provider
    assert provider.closed == 0


def test_idle_provider_cannot_be_restored_while_its_close_is_in_progress():
    close_entered = threading.Event()
    allow_close = threading.Event()
    restore_started = threading.Event()
    restore_finished = threading.Event()
    restore_errors = []

    class BlockingClose(Provider):
        def close(self):
            self.closed += 1
            close_entered.set()
            assert allow_close.wait(1)

    first, second = BlockingClose("first"), Provider("second")
    handle = SwitchableProvider(first)
    replace_thread = threading.Thread(target=lambda: handle.replace(second))

    def restore_first():
        restore_started.set()
        try:
            handle.replace(first)
        except RuntimeError as error:
            restore_errors.append(error)
        finally:
            restore_finished.set()

    restore_thread = threading.Thread(target=restore_first)
    replace_thread.start()
    assert close_entered.wait(1)
    restore_thread.start()
    assert restore_started.wait(1)
    assert not restore_finished.wait(0.1)

    allow_close.set()
    replace_thread.join(1)
    restore_thread.join(1)

    assert not replace_thread.is_alive()
    assert not restore_thread.is_alive()
    assert len(restore_errors) == 1
    assert "closed" in str(restore_errors[0]).lower()
    assert handle.current() is second
    assert first.closed == 1


def test_provider_close_can_start_thread_that_reads_current_without_deadlock():
    observed = []
    worker_blocked = []
    handle = None

    class ReadsCurrentOnClose(Provider):
        def close(self):
            worker = threading.Thread(target=lambda: observed.append(handle.current()))
            worker.start()
            worker.join(0.1)
            worker_blocked.append(worker.is_alive())
            worker.join(1)
            self.closed += 1

    old, new = ReadsCurrentOnClose("old"), Provider("new")
    handle = SwitchableProvider(old)
    handle.replace(new)

    assert worker_blocked == [False]
    assert observed == [new]


def test_provider_close_reentrant_mutations_are_rejected_without_changing_current():
    errors = []
    handle = None
    replacement = Provider("replacement")

    class ReentrantClose(Provider):
        def close(self):
            for action in (handle.close, lambda: handle.replace(Provider("intruder"))):
                try:
                    action()
                except RuntimeError as error:
                    errors.append(error)
            self.closed += 1

    old = ReentrantClose("old")
    handle = SwitchableProvider(old)
    handle.replace(replacement)

    assert len(errors) == 2
    assert handle.current() is replacement
    assert old.closed == 1


def test_slow_close_does_not_block_replacing_a_different_current_provider():
    close_entered = threading.Event()
    allow_close = threading.Event()
    switched_to_third = threading.Event()

    class SlowClose(Provider):
        def close(self):
            self.closed += 1
            close_entered.set()
            assert allow_close.wait(1)

    first, second, third = SlowClose("first"), Provider("second"), Provider("third")
    handle = SwitchableProvider(first)
    first_replace = threading.Thread(target=lambda: handle.replace(second))
    second_replace = threading.Thread(
        target=lambda: (handle.replace(third), switched_to_third.set())
    )

    first_replace.start()
    assert close_entered.wait(1)
    second_replace.start()
    assert switched_to_third.wait(0.1)
    assert handle.current() is third

    allow_close.set()
    first_replace.join(1)
    second_replace.join(1)
    assert not first_replace.is_alive()
    assert not second_replace.is_alive()
