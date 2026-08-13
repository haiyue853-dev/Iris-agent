from iris_agent.hot_radar.service import HotRadarService


def test_subscription_and_archived_items_survive_restart(tmp_path):
    service = HotRadarService(tmp_path, sources={"tech": lambda: [
        {"title": "OpenAI 发布新模型", "url": "https://example.test/model", "source": "Tech", "summary": "模型更新"},
    ]})

    subscription = service.create_subscription("OpenAI")
    result = service.scan()

    assert result.new_count == 1
    restarted = HotRadarService(tmp_path, sources={"tech": lambda: []})
    assert [item.keyword for item in restarted.list_subscriptions()] == ["OpenAI"]
    assert [item.title for item in restarted.list_items()] == ["OpenAI 发布新模型"]
    assert restarted.scan().new_count == 0


def test_scan_deduplicates_matching_news_and_reports_source_failure(tmp_path):
    item = {"title": "芯片产业新进展", "url": "https://example.test/chip", "source": "Tech", "summary": "摘要"}
    service = HotRadarService(tmp_path, sources={"tech": lambda: [item, item], "world": lambda: (_ for _ in ()).throw(RuntimeError("offline"))})
    service.create_subscription("芯片")

    result = service.scan()

    assert result.new_count == 1
    assert len(result.item_ids) == 1
    assert result.failed_sources == ("world",)
    assert result.summary == "新增 1 条热点；1 个来源不可用"
