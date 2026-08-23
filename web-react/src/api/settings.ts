import type {
  ApiProfile,
  ConnectionTestInput,
  CreateProfileInput,
  SettingsConnectionResult,
  SettingsProfilesState,
  UpdateProfileInput,
} from '../types';

const API_BASE = 'http://localhost:8000';
const PROFILES_URL = `${API_BASE}/api/settings/profiles`;

async function checked(response: Response): Promise<Response> {
  if (response.ok) return response;

  let message: unknown;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = body.detail;
      if (detail && typeof detail === 'object' && 'message' in detail) {
        message = detail.message;
      }
    }
  } catch {
    // Use the status-only fallback for non-JSON responses.
  }
  throw new Error(typeof message === 'string' && message ? message : `请求失败 (${response.status})`);
}

function jsonRequest(method: 'POST' | 'PATCH', body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function fetchSettingsProfiles(): Promise<SettingsProfilesState> {
  const response = await checked(await fetch(PROFILES_URL));
  return (await response.json()) as SettingsProfilesState;
}

export async function createSettingsProfile(payload: CreateProfileInput): Promise<ApiProfile> {
  const response = await checked(await fetch(PROFILES_URL, jsonRequest('POST', payload)));
  return (await response.json()) as ApiProfile;
}

export async function updateSettingsProfile(id: string, payload: UpdateProfileInput): Promise<ApiProfile> {
  const response = await checked(await fetch(`${PROFILES_URL}/${encodeURIComponent(id)}`, jsonRequest('PATCH', payload)));
  return (await response.json()) as ApiProfile;
}

export async function deleteSettingsProfile(id: string): Promise<void> {
  await checked(await fetch(`${PROFILES_URL}/${encodeURIComponent(id)}`, { method: 'DELETE' }));
}

export async function activateSettingsProfile(id: string): Promise<ApiProfile> {
  const response = await checked(await fetch(`${PROFILES_URL}/${encodeURIComponent(id)}/activate`, { method: 'POST' }));
  return (await response.json()) as ApiProfile;
}

export async function testSettingsProfileConnection(payload: ConnectionTestInput): Promise<SettingsConnectionResult> {
  const response = await checked(await fetch(`${PROFILES_URL}/test`, jsonRequest('POST', payload)));
  return (await response.json()) as SettingsConnectionResult;
}
