import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  activateSettingsProfile,
  createSettingsProfile,
  deleteSettingsProfile,
  fetchSettingsProfiles,
  testSettingsProfileConnection,
  updateSettingsProfile,
} from './settings';

const profile = {
  id: 'work/profile',
  name: 'Work',
  base_url: 'https://api.example.com/v1',
  model: 'iris-1',
  api_key_set: true,
  api_key_masked: 'sk-***1234',
  last_test_status: 'untested' as const,
  last_tested_at: null,
};

describe('settings profiles API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('fetches the profiles state', async () => {
    const state = { active_id: profile.id, profiles: [profile] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(state), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchSettingsProfiles()).resolves.toEqual(state);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles');
  });

  it('creates a profile with the backend request contract', async () => {
    const payload = { name: 'Work', base_url: profile.base_url, model: profile.model, api_key: 'super-secret' };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(profile), { status: 201 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createSettingsProfile(payload)).resolves.toEqual(profile);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('updates an encoded profile id with only the supplied patch', async () => {
    const patch = { name: 'Personal', api_key: 'replacement-secret', clear_api_key: false };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...profile, name: 'Personal' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await updateSettingsProfile('work/profile ?#', patch);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles/work%2Fprofile%20%3F%23', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
  });

  it('deletes an encoded profile id and does not parse the 204 response', async () => {
    const json = vi.fn(() => Promise.reject(new Error('204 must not be parsed')));
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json });
    vi.stubGlobal('fetch', fetchMock);

    await expect(deleteSettingsProfile('work/profile')).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles/work%2Fprofile', { method: 'DELETE' });
    expect(json).not.toHaveBeenCalled();
  });

  it('activates an encoded profile id without a request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(profile), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(activateSettingsProfile('work/profile')).resolves.toEqual(profile);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles/work%2Fprofile/activate', { method: 'POST' });
  });

  it('tests a connection using the profile-aware backend request contract', async () => {
    const payload = { base_url: profile.base_url, model: profile.model, api_key: 'connection-secret', profile_id: profile.id };
    const result = { ok: true, code: 'connected', message: '连接成功' };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(testSettingsProfileConnection(payload)).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/settings/profiles/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  });

  it('uses the safe backend detail message for JSON errors without leaking the payload', async () => {
    const secret = 'must-never-appear';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: 'profile_validation', message: '配置内容无效' } }),
      { status: 422 },
    )));

    const rejection = createSettingsProfile({ name: 'Work', base_url: profile.base_url, model: profile.model, api_key: secret });
    await expect(rejection).rejects.toThrow('配置内容无效');
    await expect(rejection).rejects.not.toThrow(secret);
  });

  it('falls back to the response status for non-JSON errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('gateway failure', { status: 502 })));

    await expect(fetchSettingsProfiles()).rejects.toThrow('请求失败 (502)');
  });

  it('falls back to the response status when JSON has no detail message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'unknown' } }), { status: 500 })));

    await expect(fetchSettingsProfiles()).rejects.toThrow('请求失败 (500)');
  });
});
