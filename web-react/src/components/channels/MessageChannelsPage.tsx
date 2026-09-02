import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  listMessageChannels,
  matchNapCatDirectory,
  getNapCatStatus,
  openNapCat,
  saveNapCatPath,
  sendQQTestMessage,
  websocketAddress,
  type MessageChannel,
} from '../../api/gateway';

export default function MessageChannelsPage() {
  const [qq, setQQ] = useState<MessageChannel | null>(null);
  const [qqNumber, setQQNumber] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [napcatPath, setNapcatPath] = useState('');
  const [napcatDirectory, setNapcatDirectory] = useState('');
  const [napcatRunning, setNapcatRunning] = useState(false);
  const [napcatBusy, setNapcatBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const channels = await listMessageChannels();
      setQQ(channels.find((channel) => channel.id === 'qq') || null);
      const napcat = await getNapCatStatus();
      setNapcatPath(napcat.path || '');
      setNapcatRunning(napcat.running);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取消息渠道状态');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const address = useMemo(() => websocketAddress(qq?.websocket_path || '/gateway/qq/ws'), [qq]);
  const status = !qq?.enabled ? '未启用' : qq.connected ? '已连接' : '等待连接';

  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(address);
      setNotice('连接地址已复制');
      setError('');
    } catch {
      setError('复制失败，请手动复制连接地址');
    }
  };

  const sendTest = async () => {
    setSending(true);
    try {
      await sendQQTestMessage(qqNumber.trim());
      setNotice('测试消息已发送');
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '测试消息发送失败');
      setNotice('');
    } finally {
      setSending(false);
    }
  };

  const saveNapcat = async () => {
    setNapcatBusy(true);
    try {
      const result = await saveNapCatPath(napcatPath);
      setNapcatPath(result.path);
      setNapcatRunning(result.running);
      setNotice('NapCat 路径已保存');
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'NapCat 路径保存失败');
      setNotice('');
    } finally { setNapcatBusy(false); }
  };

  const launchNapcat = async () => {
    setNapcatBusy(true);
    try {
      const result = await openNapCat();
      setNapcatRunning(result.running);
      setNotice(result.already_running ? 'NapCat 已经在运行' : 'NapCat 已启动');
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'NapCat 启动失败');
      setNotice('');
    } finally { setNapcatBusy(false); }
  };

  const matchNapcat = async () => {
    setNapcatBusy(true);
    try {
      const result = await matchNapCatDirectory(napcatDirectory);
      setNapcatPath(result.path);
      setNapcatRunning(result.running);
      setNotice(`已匹配：${result.path.split('\\').pop() || result.path}`);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'NapCat 自动匹配失败');
      setNotice('');
    } finally { setNapcatBusy(false); }
  };

  return (
    <section className="channel-page mx-auto flex w-full max-w-5xl flex-col gap-6 p-6 md:p-10" aria-label="消息渠道">
      <header className="flex flex-col gap-2">
        <span className="text-xs font-semibold tracking-[0.18em] text-neutral-500">MESSAGE CHANNELS</span>
        <h1 className="text-3xl font-semibold tracking-tight text-neutral-900">消息渠道</h1>
        <p className="max-w-2xl text-sm leading-6 text-neutral-600">查看 Iris 与聊天平台的连接状态，并完成 QQ OneBot 接入。</p>
      </header>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">{error}</div>}
      {notice && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700" role="status">{notice}</div>}

      <article className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-neutral-100 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-50 text-lg font-bold text-sky-600">QQ</div>
            <div><h2 className="text-lg font-semibold text-neutral-900">QQ</h2><p className="text-sm text-neutral-500">OneBot 11 反向 WebSocket</p></div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${qq?.connected ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{loading ? '读取中' : status}</span>
            <button type="button" onClick={() => void load()} className="rounded-lg border border-neutral-200 px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50">刷新状态</button>
          </div>
        </div>

        <div className="channel-grid grid gap-6 p-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <div className="min-w-0 space-y-5">
            <div>
              <label className="mb-2 block text-sm font-medium text-neutral-700">反向 WebSocket 地址</label>
              <div className="flex gap-2">
                <code className="min-w-0 flex-1 overflow-x-auto rounded-lg bg-neutral-950 px-4 py-3 text-sm text-neutral-100">{address}</code>
                <button type="button" onClick={() => void copyAddress()} className="rounded-lg border border-neutral-200 px-4 text-sm font-medium text-neutral-700 hover:bg-neutral-50">复制</button>
              </div>
            </div>

            <div className="rounded-xl bg-neutral-50 p-4">
              <h3 className="mb-3 text-sm font-semibold text-neutral-800">连接步骤</h3>
              <ol className="space-y-2 text-sm leading-6 text-neutral-600">
                <li>1. 保持 Iris 服务正在运行。</li>
                <li>2. 打开 NapCat 或 Lagrange 的 OneBot 配置。</li>
                <li>3. 新建反向 WebSocket，粘贴上面的地址并连接。</li>
              </ol>
            </div>

            <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-sky-100 bg-sky-50/50 p-4">
              <h3 className="text-sm font-semibold text-neutral-900">NapCat 快速启动</h3>
              <p className="mt-1 text-xs leading-5 text-neutral-500">配置 NapCat 可执行文件路径后，可直接从这里启动 QQ 客户端。</p>
              <label className="mt-4 block text-sm font-medium text-neutral-700" htmlFor="napcat-path">NapCat 可执行文件路径</label>
              <input id="napcat-path" aria-label="NapCat 可执行文件路径" value={napcatPath} onChange={(event) => setNapcatPath(event.target.value)} placeholder="例如：C:\\NapCat\\NapCat.Shell.exe" className="mt-2 block min-w-0 max-w-full w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm outline-none focus:border-sky-400" />
              <label className="mt-3 block text-sm font-medium text-neutral-700" htmlFor="napcat-directory">NapCat 文件夹（可自动匹配）</label>
              <div className="mt-2 flex gap-2">
                <input id="napcat-directory" aria-label="NapCat 文件夹路径" value={napcatDirectory} onChange={(event) => setNapcatDirectory(event.target.value)} placeholder="例如：C:\\NapCat" className="block min-w-0 flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm outline-none focus:border-sky-400" />
                <button type="button" onClick={() => void matchNapcat()} disabled={napcatBusy || !napcatDirectory} className="shrink-0 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50">自动匹配</button>
              </div>
              <div className="mt-3 flex gap-2">
                <button type="button" onClick={() => void saveNapcat()} disabled={napcatBusy} className="flex-1 rounded-lg border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50">保存路径</button>
                <button type="button" onClick={() => void launchNapcat()} disabled={napcatBusy || !napcatPath} className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-40">{napcatBusy ? '处理中…' : napcatRunning ? 'NapCat 运行中' : '打开 NapCat'}</button>
              </div>
            </div>
          </div>

          <div className="min-w-0 rounded-xl border border-neutral-200 p-4">
            <h3 className="text-sm font-semibold text-neutral-900">发送测试消息</h3>
            <p className="mt-1 text-xs leading-5 text-neutral-500">QQ 客户端连接成功后，可向指定账号发送一条测试消息。</p>
            <label className="mt-4 block text-sm font-medium text-neutral-700" htmlFor="qq-test-number">测试 QQ 号</label>
            <input id="qq-test-number" aria-label="测试 QQ 号" value={qqNumber} onChange={(event) => setQQNumber(event.target.value.replace(/\D/g, ''))} placeholder="输入 QQ 号" className="mt-2 w-full rounded-lg border border-neutral-200 px-3 py-2 text-sm outline-none focus:border-sky-400" />
            <button type="button" onClick={() => void sendTest()} disabled={!qq?.connected || !qqNumber || sending} className="mt-3 w-full rounded-lg bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">
              {sending ? '发送中…' : '发送测试消息'}
            </button>
          </div>
        </div>
      </article>
    </section>
  );
}
