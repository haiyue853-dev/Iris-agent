import { useCallback, useEffect, useRef, useState } from 'react';

import {
  deleteUserSkill,
  fetchSkills,
  fetchUserSkillContent,
  saveUserSkill,
  setSkillEnabled,
  type UserSkillContent,
  type UserSkillDraft,
} from '../api/skills';
import type { SkillInfo } from '../types';

const TOGGLE_PROCESSING_DELAY_MS = 250;

export function useSkills() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [togglingIds, setTogglingIds] = useState<Set<string>>(() => new Set());
  const [processingIds, setProcessingIds] = useState<Set<string>>(() => new Set());
  const mountedRef = useRef(true);
  const activeToggleIdsRef = useRef(new Set<string>());
  const processingTimersRef = useRef(new Map<string, ReturnType<typeof window.setTimeout>>());

  const clearProcessingTimer = useCallback((id: string) => {
    const timer = processingTimersRef.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      processingTimersRef.current.delete(id);
    }
  }, []);

  const finishToggle = useCallback((id: string) => {
    clearProcessingTimer(id);
    activeToggleIdsRef.current.delete(id);
    if (!mountedRef.current) return;

    setTogglingIds((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
    setProcessingIds((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }, [clearProcessingTimer]);

  useEffect(() => {
    const mounted = mountedRef;
    const timers = processingTimersRef.current;
    const activeToggleIds = activeToggleIdsRef.current;
    mounted.current = true;
    return () => {
      mounted.current = false;
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
      activeToggleIds.clear();
    };
  }, []);

  const reload = useCallback(async () => {
    if (!mountedRef.current) return;
    setLoading(true);
    setError('');
    try {
      const loadedSkills = await fetchSkills();
      if (mountedRef.current) setSkills(loadedSkills);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : '\u52a0\u8f7d\u5931\u8d25');
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const toggleEnabled = useCallback(async (id: string, enabled: boolean) => {
    if (!mountedRef.current || activeToggleIdsRef.current.has(id)) return;

    activeToggleIdsRef.current.add(id);
    setTogglingIds((current) => {
      const next = new Set(current);
      next.add(id);
      return next;
    });
    setError('');

    const timer = window.setTimeout(() => {
      processingTimersRef.current.delete(id);
      if (!mountedRef.current || !activeToggleIdsRef.current.has(id)) return;
      setProcessingIds((current) => {
        const next = new Set(current);
        next.add(id);
        return next;
      });
    }, TOGGLE_PROCESSING_DELAY_MS);
    processingTimersRef.current.set(id, timer);

    try {
      const updated = await setSkillEnabled(id, enabled);
      if (mountedRef.current) {
        setSkills((current) => current.map((skill) => (skill.id === id ? updated : skill)));
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : '\u5207\u6362\u5931\u8d25');
      }
    } finally {
      finishToggle(id);
    }
  }, [finishToggle]);

  const saveUserSkillDraft = useCallback(async (draft: UserSkillDraft) => {
    setError('');
    try {
      const saved = await saveUserSkill(draft);
      if (mountedRef.current) {
        setSkills((current) => {
          const index = current.findIndex((skill) => skill.id === saved.id);
          if (index === -1) return [...current, saved];
          return current.map((skill) => (skill.id === saved.id ? saved : skill));
        });
      }
    } catch (err) {
      if (mountedRef.current) setError(err instanceof Error ? err.message : '保存失败');
      throw err;
    }
  }, []);

  const loadUserSkillContent = useCallback(async (id: string): Promise<UserSkillContent> => {
    setError('');
    try {
      return await fetchUserSkillContent(id);
    } catch (err) {
      if (mountedRef.current) setError(err instanceof Error ? err.message : '加载失败');
      throw err;
    }
  }, []);

  const removeUserSkill = useCallback(async (id: string) => {
    setError('');
    try {
      await deleteUserSkill(id);
      if (mountedRef.current) setSkills((current) => current.filter((skill) => skill.id !== id));
    } catch (err) {
      if (mountedRef.current) setError(err instanceof Error ? err.message : '删除失败');
      throw err;
    }
  }, []);

  return {
    skills,
    loading,
    error,
    reload,
    toggleEnabled,
    saveUserSkill: saveUserSkillDraft,
    loadUserSkillContent,
    removeUserSkill,
    togglingIds,
    processingIds,
  };
}
