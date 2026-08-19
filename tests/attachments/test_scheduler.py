from iris_agent.attachments.scheduler import AttachmentCleanupScheduler


class Service:
    def __init__(self):
        self.calls = 0

    def cleanup_expired(self):
        self.calls += 1


def test_scheduler_cleans_once_when_started_and_stops_cleanly():
    service = Service()
    scheduler = AttachmentCleanupScheduler(service, interval_seconds=3600)

    scheduler.start()
    scheduler.stop()

    assert service.calls == 1
