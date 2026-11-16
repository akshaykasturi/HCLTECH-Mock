import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createApiClient, makeEndpoints, type Endpoints } from "../lib/api";
import type { CaseSummary, Diagnosis, HealthData } from "../lib/types";

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  loadedAt: Date | null;
}

const EMPTY: Resource<never> = { data: null, error: null, loading: false, loadedAt: null };

interface AppData {
  api: Endpoints;
  cases: Resource<CaseSummary[]>;
  health: Resource<HealthData>;
  loadCases: () => Promise<void>;
  loadHealth: () => Promise<void>;
  ensureCases: () => void;
  ensureHealth: () => void;
  /** Diagnoses received in this browser session (memory only, never written to storage). */
  diagnoses: Map<string, Diagnosis>;
  recentDiagnosisIds: string[];
  rememberDiagnosis: (diagnosis: Diagnosis) => void;
}

const AppDataContext = createContext<AppData | null>(null);

/** Load a resource; a newer call cancels the older one so results never arrive out of order. */
function useLoader<T>(fetcher: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<Resource<T>>(EMPTY);
  const controller = useRef<AbortController | null>(null);
  const requested = useRef(false);

  const load = useCallback(async () => {
    requested.current = true;
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fetcher(ctl.signal);
      if (ctl.signal.aborted) return;
      setState({ data, error: null, loading: false, loadedAt: new Date() });
    } catch (error) {
      if (ctl.signal.aborted) return;
      setState((s) => ({ ...s, loading: false, error }));
    }
  }, [fetcher]);

  const ensure = useCallback(() => {
    if (!requested.current) void load();
  }, [load]);

  return { state, load, ensure };
}

export function AppDataProvider({ children, endpoints }: { children: ReactNode; endpoints?: Endpoints }) {
  const api = useMemo(() => endpoints ?? makeEndpoints(createApiClient()), [endpoints]);
  const casesLoader = useLoader(useCallback((signal: AbortSignal) => api.cases(signal), [api]));
  const healthLoader = useLoader(useCallback((signal: AbortSignal) => api.health(signal), [api]));
  const [diagnoses, setDiagnoses] = useState<Map<string, Diagnosis>>(() => new Map());
  const [recentDiagnosisIds, setRecent] = useState<string[]>([]);

  const rememberDiagnosis = useCallback((diagnosis: Diagnosis) => {
    setDiagnoses((prev) => {
      if (prev.get(diagnosis.diagnosis_id) === diagnosis) return prev;
      const next = new Map(prev);
      next.set(diagnosis.diagnosis_id, diagnosis);
      return next;
    });
    setRecent((prev) => [diagnosis.diagnosis_id, ...prev.filter((id) => id !== diagnosis.diagnosis_id)].slice(0, 20));
  }, []);

  const value = useMemo<AppData>(() => ({
    api,
    cases: casesLoader.state,
    health: healthLoader.state,
    loadCases: casesLoader.load,
    loadHealth: healthLoader.load,
    ensureCases: casesLoader.ensure,
    ensureHealth: healthLoader.ensure,
    diagnoses,
    recentDiagnosisIds,
    rememberDiagnosis,
  }), [api, casesLoader.state, healthLoader.state, casesLoader.load, healthLoader.load, casesLoader.ensure,
       healthLoader.ensure, diagnoses, recentDiagnosisIds, rememberDiagnosis]);

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error("useAppData must be used inside AppDataProvider");
  return ctx;
}

export function useCases() {
  const { cases, loadCases, ensureCases } = useAppData();
  useEffect(() => ensureCases(), [ensureCases]);
  return { ...cases, reload: loadCases };
}

export function useHealth() {
  const { health, loadHealth, ensureHealth } = useAppData();
  useEffect(() => ensureHealth(), [ensureHealth]);
  return { ...health, reload: loadHealth };
}

/** The diagnosis with this id: from this session if known, else GET /api/diagnoses/{id}. */
export function useDiagnosis(diagnosisId: string | null) {
  const { api, diagnoses, rememberDiagnosis } = useAppData();
  const cached = diagnosisId ? diagnoses.get(diagnosisId) ?? null : null;
  const [state, setState] = useState<{ loading: boolean; error: unknown }>({ loading: false, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!diagnosisId || cached) return;
    const ctl = new AbortController();
    setState({ loading: true, error: null });
    api.diagnosis(diagnosisId, ctl.signal)
      .then((d) => {
        if (ctl.signal.aborted) return;
        rememberDiagnosis(d);
        setState({ loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!ctl.signal.aborted) setState({ loading: false, error });
      });
    return () => ctl.abort();
  }, [api, diagnosisId, cached, rememberDiagnosis, attempt]);

  return {
    diagnosis: cached,
    loading: !cached && state.loading,
    error: cached ? null : state.error,
    retry: () => setAttempt((n) => n + 1),
  };
}
