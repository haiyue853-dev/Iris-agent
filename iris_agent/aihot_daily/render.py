# -*- coding: utf-8 -*-
"""AI HOT 日报渲染器（可选）

三种输出格式，按需调用：
- to_markdown(report)   Markdown 简报 —— agent 在对话/消息里直接输出（推荐）
- to_text(report)       纯文本简报 —— 适合 SMS / 终端 / 日志
- to_html(report)       单文件 HTML 晨报 —— 淡黄+白主色调、SVG 线条图标（无 emoji）

这些渲染函数不改变 report 数据，只做展示。
"""
import html as _html

# ---------------- 版块：SVG 图标 + 暖色系（淡黄/琥珀）----------------
def _icon(paths, size=24):
    return (f'<svg viewBox="0 0 {size} {size}" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{paths}</svg>')

ICONS = {
    # 芯片（模型）
    "chip": _icon('<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'),
    # 火箭（产品）
    "rocket": _icon('<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>'
                    '<path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>'
                    '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>'),
    # 地球（行业）
    "globe": _icon('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
    # 文档（论文）
    "doc": _icon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>'),
    # 灯泡（技巧与观点）
    "bulb": _icon('<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5.76.76 1.23 1.52 1.41 2.5"/>'),
    # 报纸（页眉）
    "newspaper": _icon('<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0V9"/>'
                       '<path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6z"/>'),
    # 日历（日期）
    "calendar": _icon('<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'),
    # 上箭头（回到顶部）
    "arrow_up": _icon('<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>'),
}

SECTION_META = {
    "模型发布/更新": (ICONS["chip"], "#c9961a"),
    "产品发布/更新": (ICONS["rocket"], "#d9822b"),
    "行业动态": (ICONS["globe"], "#a8861f"),
    "论文研究": (ICONS["doc"], "#c2a11d"),
    "技巧与观点": (ICONS["bulb"], "#bb7b16"),
}


def _section_meta(label):
    return SECTION_META.get(label, (ICONS["newspaper"], "#b9972e"))


def _fallback_note(report):
    if report.is_fallback:
        src = report.fallback_from or "目标日期"
        return f"\n> 说明：{src} 当日日报尚未生成，已自动回退到最近一期（{report.date}）。\n"
    return ""


# ---------------- Markdown ----------------
def to_markdown(report, with_summary=True):
    """Markdown 简报（60秒读懂式：总结直接展示，链接附后）

    with_summary=False 时只出标题列表（更紧凑）。
    """
    lines = [
        f"# AI 早报 · {report.date_human}",
        "",
        f"> 今日共 **{report.total}** 条 · 生成于 {report.generated_at}",
    ]
    note = _fallback_note(report)
    if note:
        lines.append(note.strip())

    for sec in report.sections:
        lines.append("")
        lines.append(f"## {sec.label}（{sec.count}）")
        for it in sec.items:
            link = f" ([阅读原文]({it.url}))" if it.url else ""
            if with_summary and it.summary:
                lines.append(f"{it.no}. **{it.title}** — {it.source}{link}")
                lines.append(f"   {it.summary}")
            else:
                lines.append(f"{it.no}. **{it.title}** — {it.source}{link}")

    lines.append("")
    lines.append("---")
    lines.append(f"共 {report.total} 条 · 数据源：[AI HOT 日报]({report.daily_url}) · 版权归原作者所有")
    return "\n".join(lines)


# ---------------- 纯文本 ----------------
def to_text(report):
    """纯文本简报（无 markdown 符号，适合短信/终端）"""
    lines = [
        f"AI 早报 · {report.date_human}",
        f"今日共 {report.total} 条 · 生成于 {report.generated_at}",
    ]
    if report.is_fallback:
        lines.append(f"（注意：{report.fallback_from or '目标日期'} 当日日报未生成，已回退至 {report.date}）")
    for sec in report.sections:
        lines.append("")
        lines.append(f"【{sec.label}】{sec.count} 条")
        for it in sec.items:
            lines.append(f"{it.no}. {it.title} — {it.source}")
            if it.summary:
                lines.append(f"   {it.summary}")
            if it.url:
                lines.append(f"   原文: {it.url}")
    lines.append("")
    lines.append(f"共 {report.total} 条 · 数据源: AI HOT ({report.daily_url})")
    return "\n".join(lines)


# ---------------- HTML（单文件晨报 · 淡黄+白 / SVG 图标）----------------
def to_html(report):
    """单文件 HTML 晨报（60秒读懂式简报，淡黄+白主色调，SVG 线条图标）"""
    esc = _html.escape

    stats_html, nav_html, sections_html = [], [], []
    for si, sec in enumerate(report.sections, start=1):
        icon, color = _section_meta(sec.label)
        anchor = f"sec-{si}"
        stats_html.append(
            f'<div class="stat-chip" style="--c:{color}"><span class="stat-ico">{icon}</span>'
            f'<span class="stat-label">{esc(sec.label)}</span><span class="stat-num">{sec.count}</span></div>'
        )
        nav_html.append(
            f'<a class="nav-link" href="#{anchor}" style="--c:{color}"><span class="nav-ico">{icon}</span> {esc(sec.label)}'
            f'<span class="nav-count">{sec.count}</span></a>'
        )
        items_html = []
        for it in sec.items:
            link = esc(it.url) if it.url else "#"
            items_html.append(f"""
        <li class="brief-item">
          <span class="no" style="--c:{color}">{it.no}</span>
          <div class="item-body">
            <div class="item-head">
              <a class="item-title" href="{link}" target="_blank" rel="noopener noreferrer">{esc(it.title)}</a>
              <span class="chip">{esc(it.source)}</span>
            </div>
            <p class="item-summary">{esc(it.summary) or "（本条暂无摘要）"}</p>
            <div class="item-foot"><a class="item-link" href="{link}" target="_blank" rel="noopener noreferrer">阅读原文</a></div>
          </div>
        </li>""")
        sections_html.append(f"""
  <section class="sec" id="{anchor}">
    <div class="sec-head" style="--c:{color}">
      <span class="sec-ico">{icon}</span><h2 class="sec-title">{esc(sec.label)}</h2>
      <span class="sec-count">{sec.count} 条</span>
    </div>
    <ol class="brief-list">{''.join(items_html)}
    </ol>
  </section>""")

    fallback_badge = ""
    if report.is_fallback:
        fallback_badge = (f'<div style="margin-top:12px;background:rgba(255,255,255,.55);border:1px solid rgba(180,140,30,.35);'
                          f'padding:7px 14px;border-radius:10px;font-size:13px;color:#7a6420;">'
                          f'目标日期 {esc(report.fallback_from or "")} 当日日报尚未生成，已自动回退到最近一期</div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 早报 · {esc(report.date)}｜60秒读懂AI圈</title>
<style>
  :root {{
    --bg: #fbf6e9;            /* 淡黄米色 */
    --card: #ffffff;
    --ink: #3f3a2e;           /* 暖深灰 */
    --ink-soft: #8a7f66;
    --line: #ece3cd;          /* 淡黄描边 */
    --brand: #c9961a;         /* 琥珀金 */
    --brand-deep: #a67c14;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    background:
      radial-gradient(1100px 460px at 88% -8%, rgba(217,165,32,.10), transparent 60%),
      radial-gradient(800px 400px at -8% 0%, rgba(230,180,60,.08), transparent 55%),
      var(--bg);
    color:var(--ink); line-height:1.65;
  }}
  .wrap {{ max-width:900px; margin:0 auto; padding:0 18px 60px; }}

  /* ---------- Hero（奶油黄渐变） ---------- */
  .hero {{
    margin:26px 0 20px; padding:36px 38px 30px; border-radius:20px;
    background:linear-gradient(150deg, #fff6d9 0%, #f9e6ad 55%, #f3d98e 100%);
    border:1px solid #eed9a0; color:#5a4a1e;
    box-shadow:0 14px 34px rgba(166,124,20,.16); position:relative; overflow:hidden;
  }}
  .hero::after {{
    content:""; position:absolute; right:-60px; top:-60px; width:240px; height:240px;
    border-radius:50%; background:rgba(255,255,255,.45);
  }}
  .hero-kicker {{
    display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.6);
    border:1px solid rgba(180,140,30,.35); color:#7a6420; padding:5px 14px;
    border-radius:999px; font-size:13px; letter-spacing:.5px;
  }}
  .hero-kicker svg, .hero-date svg {{ width:15px; height:15px; }}
  .hero-title {{ font-size:30px; font-weight:800; margin:14px 0 4px; letter-spacing:.5px; color:#4a3d12; }}
  .hero-date {{ display:flex; align-items:center; gap:7px; font-size:16px; color:#6b5716; }}
  .hero-meta {{ display:flex; flex-wrap:wrap; gap:16px; margin-top:18px; align-items:center; }}
  .hero-total {{ display:flex; align-items:center; gap:10px; background:rgba(255,255,255,.55);
    border:1px solid rgba(180,140,30,.3); padding:8px 16px; border-radius:12px; color:#5a4a1e; }}
  .hero-total b {{ font-size:22px; color:#a67c14; }}
  .hero-stats {{ display:flex; flex-wrap:wrap; gap:9px; }}

  .stat-chip {{
    display:inline-flex; align-items:center; gap:7px; background:rgba(255,255,255,.55);
    border:1px solid rgba(180,140,30,.3); color:#5a4a1e; padding:5px 13px;
    border-radius:999px; font-size:13px;
  }}
  .stat-ico svg, .nav-ico svg, .sec-ico svg {{ width:16px; height:16px; }}
  .stat-ico {{ color:var(--c); display:inline-flex; }}
  .stat-num {{ min-width:21px; text-align:center; font-weight:800; font-size:12.5px;
    background:var(--c); color:#fff; border-radius:999px; padding:0 6px; line-height:19px; }}

  /* ---------- 锚点导航 ---------- */
  nav.nav {{
    position:sticky; top:0; z-index:50; display:flex; flex-wrap:wrap; gap:8px; align-items:center;
    background:rgba(255,255,255,.92); backdrop-filter:blur(10px); border:1px solid var(--line);
    border-radius:13px; padding:9px 13px; margin-bottom:26px; box-shadow:0 4px 16px rgba(166,124,20,.08);
  }}
  .nav-link {{
    text-decoration:none; color:var(--ink); font-size:13px; font-weight:600; padding:5px 11px;
    border-radius:999px; display:inline-flex; align-items:center; gap:6px; background:#fff;
    border:1px solid var(--line); transition:all .18s ease;
  }}
  .nav-ico {{ color:var(--c); display:inline-flex; }}
  .nav-link:hover {{ transform:translateY(-1px); border-color:var(--c); color:var(--c); box-shadow:0 4px 12px rgba(166,124,20,.12); }}
  .nav-count {{ font-size:11px; font-weight:800; color:#fff; background:var(--c); border-radius:999px; padding:0 6px; line-height:16px; }}
  .nav-home {{
    text-decoration:none; color:#fff; background:linear-gradient(135deg,#e2b64e,#c9961a);
    border-radius:999px; padding:5px 13px; font-size:13px; font-weight:700;
    display:inline-flex; align-items:center; gap:6px; box-shadow:0 4px 12px rgba(201,150,26,.32);
  }}
  .nav-home svg {{ width:14px; height:14px; }}

  /* ---------- 版块 ---------- */
  .sec {{ margin-bottom:34px; scroll-margin-top:78px; }}
  .sec-head {{ display:flex; align-items:center; gap:10px; margin-bottom:6px; padding-bottom:10px;
    border-bottom:2px solid color-mix(in srgb, var(--c) 50%, #e8d9a8); }}
  .sec-ico {{ width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center;
    color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fffdf5);
    border:1px solid color-mix(in srgb, var(--c) 30%, #eedfa8); }}
  .sec-title {{ font-size:20px; font-weight:800; letter-spacing:.3px; color:#4a3d12; }}
  .sec-count {{ margin-left:auto; font-size:12.5px; font-weight:700; color:var(--c);
    background:color-mix(in srgb, var(--c) 10%, #fffdf5);
    border:1px solid color-mix(in srgb, var(--c) 28%, #eedfa8);
    padding:3px 11px; border-radius:999px; }}

  /* ---------- 简报列表 ---------- */
  .brief-list {{ list-style:none; }}
  .brief-item {{ display:flex; gap:14px; padding:16px 4px; align-items:flex-start;
    border-bottom:1px dashed var(--line); }}
  .no {{ flex:0 0 auto; min-width:30px; height:30px; margin-top:1px; display:flex; align-items:center; justify-content:center;
    font-size:13.5px; font-weight:800; color:#fff;
    background:linear-gradient(135deg, var(--c), color-mix(in srgb, var(--c) 55%, #e2b64e));
    border-radius:9px; box-shadow:0 3px 8px rgba(166,124,20,.18); }}
  .item-body {{ flex:1; min-width:0; }}
  .item-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:5px; }}
  .item-title {{ font-size:15.5px; font-weight:700; color:var(--ink); text-decoration:none; line-height:1.45; }}
  .item-title:hover {{ color:var(--brand-deep); text-decoration:underline; text-underline-offset:3px; }}
  .chip {{ font-size:11px; font-weight:600; color:#6b5716; background:#f6efdc; border:1px solid #e7ddc2;
    padding:1px 8px; border-radius:999px; white-space:nowrap; max-width:46%; overflow:hidden; text-overflow:ellipsis; }}
  .item-summary {{ font-size:14px; color:var(--ink-soft); line-height:1.7; }}
  .item-foot {{ margin-top:6px; }}
  .item-link {{ font-size:12.5px; font-weight:700; color:var(--brand-deep); text-decoration:none; opacity:.88; }}
  .item-link:hover {{ opacity:1; text-decoration:underline; }}

  /* ---------- 页脚 ---------- */
  footer {{ margin-top:26px; padding:20px 22px; background:#fff; border:1px solid var(--line);
    border-radius:14px; text-align:center; color:var(--ink-soft); font-size:13.5px; }}
  footer .src {{ display:inline-flex; align-items:center; gap:8px; font-weight:800; color:#4a3d12; font-size:15px; margin-bottom:6px; }}
  footer a {{ color:var(--brand-deep); text-decoration:none; font-weight:700; }}
  footer a:hover {{ text-decoration:underline; }}

  @media (max-width:640px) {{
    .hero {{ padding:26px 20px 22px; }}
    .hero-title {{ font-size:24px; }}
    .brief-item {{ gap:10px; }}
    .item-title {{ font-size:14.5px; }}
    .chip {{ max-width:100%; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <span class="hero-kicker">{ICONS["newspaper"]} AI HOT · 60秒读懂AI圈</span>
    <h1 class="hero-title">AI 每日早报</h1>
    <div class="hero-date">{ICONS["calendar"]} {esc(report.date_human)}　·　生成于 {esc(report.generated_at)}</div>
    <div class="hero-meta">
      <div class="hero-total">今日共 <b>{report.total}</b> 条</div>
      <div class="hero-stats">{''.join(stats_html)}
      </div>
    </div>
    {fallback_badge}
  </header>
  <nav class="nav">
    <a class="nav-home" href="#top">{ICONS["arrow_up"]} 回到顶部</a>
    {''.join(nav_html)}
  </nav>
  <main id="top">
{''.join(sections_html)}
  </main>
  <footer>
    <div class="src">本日报共 {report.total} 条 · 全部总结已展示，点击「阅读原文」可深入了解</div>
    <div>数据来源：<a href="{esc(report.daily_url)}" target="_blank" rel="noopener noreferrer">AI HOT 日报 · {esc(report.date)}</a>
      （aihot.virxact.com）｜ 第三方原文版权归原作者所有</div>
    <div style="margin-top:8px;font-size:12px;opacity:.8">生成时间 {esc(report.generated_at)} · 内容由 AI HOT 每日编辑聚合</div>
  </footer>
</div>
</body>
</html>
"""
