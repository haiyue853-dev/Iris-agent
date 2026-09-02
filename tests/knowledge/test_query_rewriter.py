from iris_agent.knowledge.query_rewriter import expand_retrieval_query


def test_expands_colloquial_deleted_document_query_with_canonical_rag_terms():
    original = "资料明明已经删掉了，机器人为什么还会搜出旧答案？这种脏召回该怎么彻底处理？"

    rewritten = expand_retrieval_query(original)

    assert rewritten.startswith(original)
    assert "文档删除" in rewritten
    assert "向量库实时一致性" in rewritten
    assert "旧知识" in rewritten
    assert "脏数据" in rewritten


def test_keeps_precise_query_unchanged_when_no_colloquial_rule_matches():
    query = "Embedding 模型如何选型？中英文混合场景如何平衡效果与速度？"

    assert expand_retrieval_query(query) == query


def test_expands_multiple_versions_and_low_quality_documents_as_noise_cleanup():
    query = "知识库里同一份材料有好几个版本，还有不少水文，入库前后怎么清理？"

    rewritten = expand_retrieval_query(query)

    assert "噪声文档" in rewritten
    assert "重复文档" in rewritten
    assert "文档去重" in rewritten
    assert "过滤" in rewritten
