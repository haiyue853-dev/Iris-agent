import { useCallback, useEffect, useState } from 'react';
import { fetchLatestDaily, fetchDailyByDate } from '../../api/aihotDaily';
import { fetchWorldNews } from '../../api/worldNews';
import { fetchTechNews } from '../../api/techNews';
import type { AihotDailyReport, AihotDailySection, WorldNewsItem, TechNewsItem } from '../../types';

/* ---------------- SVG 线条图标（无 emoji） ---------------- */
const ICON_PATHS: Record<string, string> = {
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  rocket: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  bulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5.76.76 1.23 1.52 1.41 2.5"/>',
  newspaper: '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0V9"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>',
};

function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] || '' }}
    />
  );
}

const SECTION_COLORS: Record<string, string> = {
  '模型发布/更新': '#6e6e73',
  '产品发布/更新': '#6e6e73',
  '行业动态': '#6e6e73',
  '论文研究': '#6e6e73',
  '技巧与观点': '#6e6e73',
};

function sectionColor(label: string): string {
  return SECTION_COLORS[label] || '#6e6e73';
}

function sectionIcon(label: string): string {
  switch (label) {
    case '模型发布/更新': return 'chip';
    case '产品发布/更新': return 'rocket';
    case '行业动态': return 'globe';
    case '论文研究': return 'doc';
    case '技巧与观点': return 'bulb';
    default: return 'newspaper';
  }
}

/* ---------------- 日期选择器 ---------------- */
function todayStr(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

/** YYYY-MM-DD → MM月DD日（跨年带年份） */
function humanTime(time: string): string {
  if (!time) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(time);
  if (!m) return time;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const now = new Date();
  return year === now.getFullYear() ? `${month}月${day}日` : `${year}年${month}月${day}日`;
}

/* ---------------- 页面 ---------------- */

// 模块级缓存：切换视图/刷新时避免"从无到有"闪变，先显示上次数据再静默刷新
let cachedReport: AihotDailyReport | null = null;
let cachedWorld: WorldNewsItem[] = [];
let cachedTech: TechNewsItem[] = [];

export default function AihotDailyPage() {
  const [report, setReport] = useState<AihotDailyReport | null>(cachedReport);
  const [date, setDate] = useState(cachedReport?.date ?? todayStr());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [worldItems, setWorldItems] = useState<WorldNewsItem[]>(cachedWorld);
  const [worldLoading, setWorldLoading] = useState(cachedWorld.length === 0);
  const [worldError, setWorldError] = useState('');
  const [techItems, setTechItems] = useState<TechNewsItem[]>(cachedTech);
  const [techLoading, setTechLoading] = useState(cachedTech.length === 0);
  const [techError, setTechError] = useState('');

  // 时政热点（页面底部栏目，独立于 AI 日报数据）
  const loadWorld = useCallback(async () => {
    setWorldLoading(true);
    setWorldError('');
    try {
      const items = await fetchWorldNews();
      cachedWorld = items;
      setWorldItems(items);
    } catch (err) {
      setWorldError(err instanceof Error ? err.message : '时政热点加载失败');
    } finally {
      setWorldLoading(false);
    }
  }, []);

  // 计算机行业新闻（替换 AI HOT 的「行业动态」）
  const loadTech = useCallback(async () => {
    setTechLoading(true);
    setTechError('');
    try {
      const items = await fetchTechNews();
      cachedTech = items;
      setTechItems(items);
    } catch (err) {
      setTechError(err instanceof Error ? err.message : '行业动态加载失败');
    } finally {
      setTechLoading(false);
    }
  }, []);

  // 按日期加载 AI 日报
  const load = useCallback(async (target: string) => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchDailyByDate(target);
      cachedReport = data;
      setReport(data);
      setDate(data.date);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLatestDaily()
      .then((data) => {
        cachedReport = data;
        setReport(data);
        setDate(data.date);
      })
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'));
    loadWorld();
    loadTech();
  }, [loadWorld, loadTech]);

  const handleDateChange = (value: string) => {
    if (!value) return;
    load(value);
  };

  const handleRefresh = () => {
    fetchLatestDaily()
      .then((data) => {
        cachedReport = data;
        setReport(data);
        setDate(data.date);
        setError('');
      })
      .catch((err) => setError(err instanceof Error ? err.message : '刷新失败'));
    loadWorld(); // 时政栏目同步刷新
    loadTech(); // 行业动态同步刷新
  };

  return (
    <div className="aihot-page">
      {/* Hero */}
      <header className="aihot-hero">
        <div className="aihot-hero-top">
          <span className="aihot-kicker"><Icon name="newspaper" size={15} /> AI HOT · 60秒读懂AI圈</span>
          <button className="aihot-refresh" onClick={handleRefresh} title="刷新为最新一期">
            <Icon name="refresh" size={15} /> 刷新
          </button>
        </div>
        <h1 className="aihot-title">AI 每日早报</h1>
        <div className="aihot-hero-date">
          <Icon name="calendar" size={15} />
          {report ? report.date_human : '加载中…'}　·　生成于 {report ? report.generated_at : '…'}
        </div>
        {report && (
          <div className="aihot-meta">
            <div className="aihot-total">今日共 <b>{report.total}</b> 条</div>
            <div className="aihot-date-picker">
              <input
                type="date"
                value={date}
                max={todayStr()}
                onChange={(e) => handleDateChange(e.target.value)}
                title="查看指定日期"
              />
            </div>
          </div>
        )}
        {report?.is_fallback && (
          <div className="aihot-fallback">
            目标日期 {report.fallback_from || ''} 当日日报尚未生成，已自动回退到最近一期（{report.date}）
          </div>
        )}
      </header>

      {error && <div className="aihot-error">{error}</div>}
      {loading && <div className="aihot-loading">加载中…</div>}

      {/* 锚点导航 */}
      {report && !error && (
        <nav className="aihot-nav">
          {report.sections.filter((sec) => sec.label !== '行业动态').map((sec, i) => (
            <a
              key={sec.label}
              className="aihot-nav-link"
              style={{ ['--c' as string]: sectionColor(sec.label) }}
              href={`#aihot-sec-${i + 1}`}
            >
              <span className="aihot-nav-ico"><Icon name={sectionIcon(sec.label)} size={14} /></span>
              {sec.label}
              <span className="aihot-nav-count">{sec.count}</span>
            </a>
          ))}
          <a
            className="aihot-nav-link"
            style={{ ['--c' as string]: '#6e6e73' }}
            href="#aihot-sec-tech"
          >
            <span className="aihot-nav-ico"><Icon name="chip" size={14} /></span>
            行业动态 · 计算机
            {!techLoading && !techError && <span className="aihot-nav-count">{techItems.length}</span>}
          </a>
          <a
            className="aihot-nav-link"
            style={{ ['--c' as string]: '#6e6e73' }}
            href="#aihot-sec-world"
          >
            <span className="aihot-nav-ico"><Icon name="globe" size={14} /></span>
            时政热点
            {!worldLoading && !worldError && <span className="aihot-nav-count">{worldItems.length}</span>}
          </a>
        </nav>
      )}

      {/* 正文：60秒读懂式列表（AI HOT，行业动态替换为计算机行业新闻） */}
      {report && !error && (
        <main className="aihot-main">
          {(() => {
            let globalNo = 0;
            return report.sections
              .filter((sec: AihotDailySection) => sec.label !== '行业动态')
              .map((sec: AihotDailySection, i: number) => (
                <section key={sec.label} className="aihot-sec" id={`aihot-sec-${i + 1}`}>
                  <div className="aihot-sec-head" style={{ ['--c' as string]: sectionColor(sec.label) }}>
                    <span className="aihot-sec-ico"><Icon name={sectionIcon(sec.label)} size={17} /></span>
                    <h2 className="aihot-sec-title">{sec.label}</h2>
                    <span className="aihot-sec-count">{sec.count} 条</span>
                  </div>
                  <ol className="aihot-list">
                    {sec.items.map((it) => {
                      globalNo += 1;
                      return (
                        <li key={it.no} className="aihot-item">
                          <span className="aihot-no" style={{ ['--c' as string]: sectionColor(sec.label) }}>{globalNo}</span>
                          <div className="aihot-item-body">
                            <div className="aihot-item-head">
                              <a
                                className="aihot-item-title"
                                href={it.url_original || it.url_aihot}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {it.title}
                              </a>
                              <span className="aihot-chip">{it.source}</span>
                            </div>
                            <p className="aihot-item-summary">{it.summary || '（本条暂无摘要）'}</p>
                            <div className="aihot-item-foot">
                              <a
                                className="aihot-item-link"
                                href={it.url_original || it.url_aihot}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                阅读原文
                              </a>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              ));
          })()}
        </main>
      )}

      {/* 行业动态 · 计算机（IT之家 + 网易科技，替换 AI HOT 行业动态） */}
      <div className="aihot-main">
        <section className="aihot-sec" id="aihot-sec-tech">
          <div className="aihot-sec-head">
            <span className="aihot-sec-ico" style={{ color: '#6e6e73' }}>
              <Icon name="chip" size={17} />
            </span>
            <h2 className="aihot-sec-title">行业动态 · 计算机</h2>
            {!techLoading && !techError && <span className="aihot-sec-count">{techItems.length} 条</span>}
          </div>

          {techError && <div className="aihot-error">{techError}</div>}
          {techLoading && <div className="aihot-loading">行业动态加载中…</div>}

          {!techLoading && !techError && (
            <ol className="aihot-list">
              {techItems.map((it, idx) => (
                <li key={`${it.url}-${idx}`} className="aihot-item">
                  <span className="aihot-no" style={{ background: '#6e6e73' }}>{idx + 1}</span>
                  <div className="aihot-item-body">
                    <div className="aihot-item-head">
                      <a
                        className="aihot-item-title"
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {it.title}
                      </a>
                      <span className="aihot-chip">{it.source}</span>
                    </div>
                    {it.summary && <p className="aihot-item-summary">{it.summary}</p>}
                    <div className="aihot-item-foot">
                      <span className="aihot-item-time">{humanTime(it.time)}</span>
                      <a
                        className="aihot-item-link"
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ marginLeft: '12px' }}
                      >
                        阅读原文
                      </a>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      {/* 时政热点栏目（世界，独立于 AI 日报数据） */}
      <div className="aihot-main">
        <section className="aihot-sec" id="aihot-sec-world">
          <div className="aihot-sec-head">
            <span className="aihot-sec-ico" style={{ color: '#6e6e73' }}>
              <Icon name="globe" size={17} />
            </span>
            <h2 className="aihot-sec-title">时政热点 · 世界</h2>
            {!worldLoading && !worldError && <span className="aihot-sec-count">{worldItems.length} 条</span>}
          </div>

          {worldError && <div className="aihot-error">{worldError}</div>}
          {worldLoading && <div className="aihot-loading">时政热点加载中…</div>}

          {!worldLoading && !worldError && (
            <ol className="aihot-list">
              {worldItems.map((it, idx) => (
                <li key={`${it.url}-${idx}`} className="aihot-item">
                  <span className="aihot-no" style={{ background: '#6e6e73' }}>{idx + 1}</span>
                  <div className="aihot-item-body">
                    <div className="aihot-item-head">
                      <a
                        className="aihot-item-title"
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {it.title}
                      </a>
                      <span className="aihot-chip">{it.source}</span>
                    </div>
                    {it.summary && <p className="aihot-item-summary">{it.summary}</p>}
                    <div className="aihot-item-foot">
                      <span className="aihot-item-time">{humanTime(it.time)}</span>
                      <a
                        className="aihot-item-link"
                        href={it.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ marginLeft: '12px' }}
                      >
                        阅读原文
                      </a>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      {report && !error && (
        <footer className="aihot-footer">
          <div className="aihot-footer-src">本日报共 {report.total} 条 · 全部总结已展示，点击「阅读原文」可深入了解</div>
          <div>
            数据来源：<a href={report.daily_url} target="_blank" rel="noopener noreferrer">AI HOT 日报 · {report.date}</a>
            （aihot.virxact.com）｜ 第三方原文版权归原作者所有
          </div>
        </footer>
      )}
    </div>
  );
}
