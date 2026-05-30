import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { BreadthPage } from "./features/breadth/BreadthPage";
import { StrongPage } from "./features/strong/StrongPage";

const routerBasename = import.meta.env.BASE_URL.replace(/\/$/, "") || undefined;

export default function App() {
  return (
    <BrowserRouter basename={routerBasename}>
      <Routes>
        <Route path="/" element={<Navigate to="/strong" replace />} />
        <Route path="/strong" element={<StrongPage />} />
        <Route path="/breadth" element={<BreadthPage />} />
        <Route path="*" element={<Navigate to="/strong" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
