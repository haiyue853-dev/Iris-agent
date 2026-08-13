from iris_agent.notifications.service import NotificationService


def test_notification_service_persists_and_marks_read(tmp_path):
    service = NotificationService(tmp_path)
    notification = service.create("radar scan", "one new item", "task-1", ("item-1",))

    assert service.list_notifications()[0].read is False
    assert service.mark_read(notification.id).read is True
    assert NotificationService(tmp_path).list_notifications()[0].item_ids == ("item-1",)


def test_notification_service_deletes_notification(tmp_path):
    service = NotificationService(tmp_path)
    notification = service.create("radar scan", "one new item", "task-1", ("item-1",))

    service.delete(notification.id)

    assert service.list_notifications() == []
