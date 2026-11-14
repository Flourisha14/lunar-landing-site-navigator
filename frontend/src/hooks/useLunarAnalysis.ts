import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, lunarApi } from '../api/client';
import type { GeometryResponse, HealthResponse, MetadataResponse, SiteAnalysisResponse } from '../api/types';
import type { SimulationState } from '../state/simulation';
import { buildRequests } from '../utils/validation';

export type RequestOutcome<T> = { value: T | null; error: string | null };
const empty = <T,>(): RequestOutcome<T> => ({ value: null, error: null });
const errorText = (error: unknown): string => error instanceof ApiError
  ? `${error.message}${error.code ? ` [${error.code}]` : ''}${error.status ? ` (HTTP ${error.status})` : ''}`
  : error instanceof Error ? error.message : String(error);

export function useLunarAnalysis() {
  const [health, setHealth] = useState<RequestOutcome<HealthResponse>>(empty);
  const [metadata, setMetadata] = useState<RequestOutcome<MetadataResponse>>(empty);
  const [geometry, setGeometry] = useState<RequestOutcome<GeometryResponse>>(empty);
  const [analysis, setAnalysis] = useState<RequestOutcome<SiteAnalysisResponse>>(empty);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const running = useRef<AbortController | null>(null);

  const checkConnection = useCallback(async () => {
    setChecking(true);
    const [healthResult, metadataResult] = await Promise.allSettled([lunarApi.health(), lunarApi.metadata()]);
    setHealth(healthResult.status === 'fulfilled'
      ? { value: healthResult.value, error: null }
      : { value: null, error: errorText(healthResult.reason) });
    setMetadata(metadataResult.status === 'fulfilled'
      ? { value: metadataResult.value, error: null }
      : { value: null, error: errorText(metadataResult.reason) });
    setChecking(false);
  }, []);

  useEffect(() => { void checkConnection(); }, [checkConnection]);
  useEffect(() => () => running.current?.abort(), []);

  const analyze = useCallback(async (simulation: SimulationState) => {
    running.current?.abort();
    setInputError(null);
    setGeometry(empty());
    setAnalysis(empty());
    let requests: ReturnType<typeof buildRequests>;
    try {
      requests = buildRequests(simulation);
    } catch (error) {
      setInputError(errorText(error));
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    running.current = controller;
    setLoading(true);
    const [geometryResult, analysisResult] = await Promise.allSettled([
      lunarApi.geometry(requests.geometry, controller.signal),
      lunarApi.siteAnalysis(requests.analysis, controller.signal),
    ]);
    if (controller.signal.aborted) return;
    setGeometry(geometryResult.status === 'fulfilled'
      ? { value: geometryResult.value, error: null }
      : { value: null, error: errorText(geometryResult.reason) });
    setAnalysis(analysisResult.status === 'fulfilled'
      ? { value: analysisResult.value, error: null }
      : { value: null, error: errorText(analysisResult.reason) });
    setLoading(false);
    running.current = null;
  }, []);

  return { health, metadata, geometry, analysis, loading, checking, inputError, checkConnection, analyze };
}
