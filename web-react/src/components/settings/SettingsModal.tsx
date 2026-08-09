import { useEffect, useState } from 'react';
import { fetchSettings, updateSettings } from '../../api/settings';

interface SettingsModalProps {
  onClose: () => void;
}

export default function SettingsModal({ onClose }: SettingsModalProps) {
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKeySet, setApiKeySet] = useState(false);
  const [apiKeyMasked, setApiKeyMasked] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((s) => {
        setBaseUrl(s.base_url);
        setModel(s.model);
        setApiKeySet(s.api_key_set);
        setApiKeyMasked(s.api_key_masked);
      })
      .catch((err) => setMessage({ type: 'err', text: err instanceof Error ? err.message : '加载配置失败' }))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const patch: { api_key?: string; base_url?: string; model?: string } = {};
      if (apiKey.trim()) patch.api_key = apiKey.trim();
      if (baseUrl.trim()) patch.base_url = baseUrl.trim();
      if (model.trim()) patch.model = model.trim();
      if (Object.keys(patch).length === 0) {
        setMessage({ type: 'err', text: '没有需要保存的修改' });
        return;
      }
      const updated = await updateSettings(patch);
      setApiKey('');
      setApiKeySet(updated.api_key_set);
      setApiKeyMasked(updated.api_key_masked);
      setBaseUrl(updated.base_url);
      setModel(updated.model);
      setMessage({ type: 'ok', text: '已保存，立即生效' });
    } catch (err) {
      setMessage({ type: 'err', text: err instanceof Error ? err.message : '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-head">
          <h3 className="settings-title">设置</h3>
          <button className="settings-close" onClick={onClose} title="关闭">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {loading ? (
          <div className="settings-loading">加载中…</div>
        ) : (
          <>
            <div className="settings-body">
              <div className="settings-field">
                <label className="settings-label">
                  API Key
                  {apiKeySet ? (
                    <span className="settings-badge ok">已设置 {apiKeyMasked}</span>
                  ) : (
                    <span className="settings-badge warn">未设置</span>
                  )}
                </label>
                <input
                  type="password"
                  className="settings-input"
                  placeholder={apiKeySet ? '输入新 Key 以替换（留空则保持不变）' : 'sk-…'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="off"
                />
                <p className="settings-hint">仅保存到本地 .env 文件，不经过第三方</p>
              </div>

              <div className="settings-field">
                <label className="settings-label">Base URL</label>
                <input
                  type="text"
                  className="settings-input"
                  placeholder="https://api.deepseek.com/v1"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                />
              </div>

              <div className="settings-field">
                <label className="settings-label">模型</label>
                <input
                  type="text"
                  className="settings-input"
                  placeholder="deepseek-chat"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                />
              </div>
            </div>

            {message && <div className={`settings-message ${message.type}`}>{message.text}</div>}

            <div className="settings-foot">
              <button className="settings-btn primary" onClick={handleSave} disabled={saving}>
                {saving ? '保存中…' : '保存'}
              </button>
              <button className="settings-btn" onClick={onClose}>取消</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
