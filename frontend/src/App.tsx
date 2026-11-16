import type { ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import type { Endpoints } from "./lib/api";
import { AppDataProvider } from "./state/AppData";
import { ToastProvider } from "./state/Toasts";
import { AppShell } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { CasesPage } from "./pages/CasesPage";
import { DiagnosisPage } from "./pages/DiagnosisPage";
import { SavedDiagnosisPage } from "./pages/SavedDiagnosisPage";
import { EvidencePage } from "./pages/EvidencePage";
import { ReviewPage } from "./pages/ReviewPage";
import { AuditPage } from "./pages/AuditPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export function AppProviders({ children, endpoints }: { children: ReactNode; endpoints?: Endpoints }) {
  return (
    <ToastProvider>
      <AppDataProvider endpoints={endpoints}>{children}</AppDataProvider>
    </ToastProvider>
  );
}

/** Routes. "/system-health" (not "/health") so the page never collides with the backend's /health endpoint. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="diagnosis" element={<DiagnosisPage />} />
        <Route path="diagnosis/:caseId" element={<DiagnosisPage />} />
        <Route path="diagnoses/:diagnosisId" element={<SavedDiagnosisPage />} />
        <Route path="evidence" element={<EvidencePage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="system-health" element={<SystemHealthPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AppProviders>
      <AppRoutes />
    </AppProviders>
  );
}
