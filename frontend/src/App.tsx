import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { BreadthPage } from "./features/breadth/BreadthPage";
import { StrongPage } from "./features/strong/StrongPage";
import { useAutomationEnsure } from "./hooks/useAutomationEnsure";

const routerBasename = import.meta.env.BASE_URL.replace(/\/$/, "") || undefined;

function AppRoutes() {
  useAutomationEnsure();
  return (
      <Routes>
        <Route path="/" element={<Navigate to="/strong" replace />} />
        <Route path="/strong" element={<StrongPage />} />
        <Route path="/breadth" element={<BreadthPage />} />
        <Route path="*" element={<Navigate to="/strong" replace />} />
      </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={routerBasename}>
      <AppRoutes />
    </BrowserRouter>
  );
}
