import { useCallback, useRef, useState } from 'react';
import { analyzeUml } from '../../api/uml';
import type { UmlDiagramType } from '../../types';
import DrawioEditor from './DrawioEditor';
import { hasSavedDrawioDiagram } from './drawioStorage';

const DIAGRAM_OPTIONS: { value: UmlDiagramType; label: string }[] = [
  { value: 'flowchart', label: '流程图 flowchart' },
  { value: 'activity', label: '活动图 activity' },
  { value: 'usecase', label: '用例图 usecase' },
  { value: 'sequenceDiagram', label: '时序图 sequenceDiagram' },
  { value: 'classDiagram', label: '类图 classDiagram' },
  { value: 'erDiagram', label: 'ER 图 erDiagram' },
];

const EXAMPLES = [
  { label: '登录流程', text: '用户登录流程：输入账号密码，校验通过进入首页，失败提示重试，连续失败 5 次锁定账号 30 分钟。' },
  { label: '订单处理', text: '电商下单流程：用户提交订单，系统校验库存，库存充足则扣减库存并创建支付单，支付成功通知仓库发货；库存不足则提示缺货并允许预约。' },
];

export default function UmlFlowPage() {
  const [prompt, setPrompt] = useState('');
  const [diagramType, setDiagramType] = useState<UmlDiagramType>('flowchart');
  const [generating, setGenerating] = useState(false);
  const [apiError, setApiError] = useState('');
  const [mermaidCode, setMermaidCode] = useState('');
  const [drawioImportRequest, setDrawioImportRequest] = useState<number | null>(null);
  const nextDrawioImportRequestRef = useRef(0);
  const [hasDrawioContent, setHasDrawioContent] = useState(false);
  const resultRef = useRef<HTMLDivElement | null>(null);

  const importMermaidToProfessionalCanvas = useCallback(
    (code = mermaidCode) => {
      if (!code.trim()) return;
      if (
        (hasDrawioContent || hasSavedDrawioDiagram()) &&
        !window.confirm('当前专业画布已有已编辑内容。导入 Mermaid 会替换画布内容，是否继续？')
      ) {
        return;
      }
      nextDrawioImportRequestRef.current += 1;
      setMermaidCode(code);
      setDrawioImportRequest(nextDrawioImportRequestRef.current);
    },
    [hasDrawioContent, mermaidCode]
  );

  const handleGenerate = async () => {
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    setApiError('');
    try {
      const result = await analyzeUml(prompt.trim(), diagramType);
      setMermaidCode(result.mermaid);
      importMermaidToProfessionalCanvas(result.mermaid);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '生成失败，请稍后重试');
    } finally {
      setGenerating(false);
    }
  };

  const handleDrawioImportConsumed = useCallback((request: number) => {
    setDrawioImportRequest((current) => (current === request ? null : current));
  }, []);

  const copyCode = async () => {
    if (!mermaidCode) return;
    try {
      await navigator.clipboard.writeText(mermaidCode);
    } catch {
      // Clipboard access can be unavailable in some browsers.
    }
  };

  const downloadMmd = () => {
    if (!mermaidCode) return;
    const blob = new Blob([mermaidCode], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `flowchart-${Date.now()}.mmd`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const hasResult = mermaidCode.trim().length > 0;

  return (
    <div className="uml-page">
      <div className="uml-input-card">
        <div className="uml-card-head">
          <span className="uml-card-title">生成流程图</span>
          <span className="uml-card-desc">描述你的需求，或直接粘贴代码，AI 将分析并生成 Mermaid 图表</span>
        </div>
        <textarea
          className="uml-input"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={'例如：\n用户登录流程：输入账号密码，校验通过进入首页，失败提示重试，连续失败 5 次锁定账号。\n\n或直接粘贴一段 Python / JS / Java 代码…'}
          rows={5}
        />
        <div className="uml-input-foot">
          <div className="uml-examples">
            {EXAMPLES.map((example) => (
              <button key={example.label} className="uml-example-btn" onClick={() => setPrompt(example.text)}>
                {example.label}
              </button>
            ))}
          </div>
          <div className="uml-actions">
            <select className="uml-select" value={diagramType} onChange={(event) => setDiagramType(event.target.value as UmlDiagramType)}>
              {DIAGRAM_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button className="uml-generate-btn" onClick={handleGenerate} disabled={!prompt.trim() || generating}>
              {generating ? (
                <>
                  <span className="uml-spinner" />
                  分析生成中…
                </>
              ) : (
                '生成流程图'
              )}
            </button>
          </div>
        </div>
        {apiError && <div className="uml-error">{apiError}</div>}
      </div>

      <div className="uml-result" ref={resultRef}>
        <div className="uml-toolbar">
          <span className="uml-toolbar-type">
            {DIAGRAM_OPTIONS.find((option) => option.value === diagramType)?.label}
            <span className="uml-toolbar-tag">专业画布</span>
          </span>
          <div className="uml-toolbar-btns">
            <button className="uml-tool-btn" onClick={() => importMermaidToProfessionalCanvas()} disabled={!hasResult}>
              重新导入到专业画布
            </button>
            <button className="uml-tool-btn" onClick={copyCode} title="复制 Mermaid 源码">
              复制源码
            </button>
            <button className="uml-tool-btn" onClick={downloadMmd} title="下载 .mmd 源码文件">
              下载 .mmd
            </button>
          </div>
        </div>

        <DrawioEditor
          mermaidCode={mermaidCode}
          importRequest={drawioImportRequest ?? 0}
          onImportConsumed={handleDrawioImportConsumed}
          onDiagramPresenceChange={setHasDrawioContent}
          onSavedDiagramChange={setHasDrawioContent}
        />

        <div className="uml-editor uml-editor-professional-source">
          <label className="uml-editor-head" htmlFor="uml-mermaid-source">
            Mermaid 源码
            <span className="uml-editor-hint">编辑后点击“重新导入到专业画布”才会替换 Draw.io 内容</span>
          </label>
          <textarea
            id="uml-mermaid-source"
            aria-label="Mermaid 源码"
            className="uml-editor-textarea uml-editor-textarea-short"
            value={mermaidCode}
            onChange={(event) => setMermaidCode(event.target.value)}
            spellCheck={false}
          />
        </div>
      </div>
    </div>
  );
}
