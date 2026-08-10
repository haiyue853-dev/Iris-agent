import { useCallback, useEffect, useState } from 'react';

import { fetchSkills, setSkillEnabled } from '../api/skills';
import type { SkillInfo } from '../types';

export function useSkills() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSkills(await fetchSkills());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const toggleEnabled = useCallback(async (id: string, enabled: boolean) => {
    setTogglingId(id);
    setError('');
    try {
      const updated = await setSkillEnabled(id, enabled);
      setSkills((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch (err) {
      setError(err instanceof Error ? err.message : '切换失败');
    } finally {
      setTogglingId(null);
    }
  }, []);

  return { skills, loading, error, reload, toggleEnabled, togglingId };
}
