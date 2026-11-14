import type {
  ApiErrorBody, GeometryRequest, GeometryResponse, HealthResponse,
  MetadataResponse, SiteAnalysisRequest, SiteAnalysisResponse,
} from './types';

const DEFAULT_API_URL = 'http://127.0.0.1:8000';
export const API_BASE_URL = (import.meta.env.VITE_LUNAR_API_URL || DEFAULT_API_URL).replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, public readonly status: number | null, public readonly code: string | null = null) {
    super(message);
    this.name = 'ApiError';
  }
}

function describeError(body: ApiErrorBody | null, fallback: string): string {
  if (!body?.detail) return fallback;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((item) => `${item.loc?.join('.') ?? 'request'}: ${item.msg ?? 'invalid value'}`).join('; ');
  }
  return fallback;
}

async function request<T>(path: string, data?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Unable to connect to the scientific API. Check that FastAPI is running and CORS allows the frontend origin.', null);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiErrorBody | null;
    throw new ApiError(describeError(body, `API returned HTTP ${response.status}`), response.status, body?.code ?? null);
  }
  try {
    return await response.json() as T;
  } catch {
    throw new ApiError('Scientific API returned invalid JSON.', response.status, 'invalid_response');
  }
}

export const lunarApi = {
  health: (signal?: AbortSignal) => request<HealthResponse>('/api/v1/health', undefined, signal),
  metadata: (signal?: AbortSignal) => request<MetadataResponse>('/api/v1/metadata', undefined, signal),
  geometry: (data: GeometryRequest, signal?: AbortSignal) => request<GeometryResponse>('/api/v1/geometry', data, signal),
  siteAnalysis: (data: SiteAnalysisRequest, signal?: AbortSignal) => request<SiteAnalysisResponse>('/api/v1/site-analysis', data, signal),
};
