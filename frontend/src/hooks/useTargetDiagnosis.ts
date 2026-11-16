import { useSearchParams } from "react-router-dom";
import { useAppData, useDiagnosis } from "../state/AppData";

/** The diagnosis a page works on: ?d=<diagnosis_id>, else the most recent one from this session. */
export function useTargetDiagnosis() {
  const [params] = useSearchParams();
  const { recentDiagnosisIds } = useAppData();
  const fromUrl = params.get("d");
  const diagnosisId = fromUrl || recentDiagnosisIds[0] || null;
  return { diagnosisId, fromUrl: Boolean(fromUrl), ...useDiagnosis(diagnosisId) };
}
