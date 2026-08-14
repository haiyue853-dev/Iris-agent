import io
import json

from iris_agent.interview_knowledge import mcp_server


def test_mcp_server_advertises_read_and_write_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    mcp_server.serve(tmp_path / "knowledge.json")

    tools = json.loads(output.getvalue().splitlines()[1])["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["search_interview_sources", "extract_interview_qa", "save_interview_qa"]
    assert tools[0]["annotations"]["readOnlyHint"] is True
    assert "annotations" not in tools[2]


def test_search_uses_bing_results_before_falling_back_to_other_providers(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "_fetch",
        lambda url: '<li class="b_algo"><h2><a href="https://example.com/questions">Python &amp; answers</a></h2></li>',
    )

    results = mcp_server._search_sources("Python", 3)

    assert results == [{"url": "https://example.com/questions", "title": "Python & answers"}]


def test_search_decodes_bing_links_and_ranks_interview_pages_first(monkeypatch):
    monkeypatch.setattr(mcp_server, "_public_url", lambda url: url)
    monkeypatch.setattr(
        mcp_server,
        "_fetch",
        lambda url: (
            '<li class="b_algo"><h2><a href="https://www.oracle.com/java/">Java Software</a></h2></li>'
            '<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9qYXZhLWludGVydmlldy1xdWVzdGlvbnM%3D&amp;ntb=1">Java Interview Questions and Answers</a></h2></li>'
        ),
    )

    results = mcp_server._search_sources("Java", 1)

    assert results == [{"url": "https://example.com/java-interview-questions", "title": "Java Interview Questions and Answers"}]


def test_search_query_removes_duplicate_interview_terms():
    assert mcp_server._search_query("Java interview questions and answers") == '"Java interview questions"'
    assert mcp_server._search_query("AI Agent 开发面试经验") == '"AI Agent 开发 interview questions"'


def test_bing_rss_parser_returns_direct_source_links():
    results = mcp_server._parse_bing_rss(
        "<rss><channel><item><title>Java Interview Questions</title>"
        "<link>https://example.com/java-interview</link></item></channel></rss>"
    )

    assert results == [{"url": "https://example.com/java-interview", "title": "Java Interview Questions"}]


def test_extracts_numbered_questions_with_following_answer_blocks():
    value = """
    <h2>1. What is the JVM?</h2>
    <p>The JVM executes Java bytecode on the current operating system.</p>
    <p>It also manages memory and garbage collection.</p>
    <h2>2. What is JIT?</h2>
    <p>The JIT compiler turns frequently executed bytecode into native machine code.</p>
    """

    items = mcp_server._extract(value, "https://example.com/java", 10)

    assert items == [
        {
            "question": "What is the JVM?",
            "answer": "The JVM executes Java bytecode on the current operating system. It also manages memory and garbage collection.",
            "source_url": "https://example.com/java",
        },
        {
            "question": "What is JIT?",
            "answer": "The JIT compiler turns frequently executed bytecode into native machine code.",
            "source_url": "https://example.com/java",
        },
    ]


def test_html_decoder_falls_back_to_gb18030_for_chinese_pages():
    assert mcp_server._decode_html("Java 面试题".encode("gb18030"), "utf-8") == "Java 面试题"


def test_server_supports_streams_without_encoding_reconfiguration(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"invalid"}\n'))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    mcp_server.serve(tmp_path / "knowledge.json")

    assert "error" in output.getvalue()
