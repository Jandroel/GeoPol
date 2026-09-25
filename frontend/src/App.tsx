import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { Runs } from "./pages/Runs";
import { NewRun, UploadWorkspaceProvider } from "./pages/NewRun";
import { RunDetail } from "./pages/RunDetail";
import { Review } from "./pages/Review";
import { ResultDetail } from "./pages/ResultDetail";
import { References } from "./pages/References";
import { Rules } from "./pages/Rules";
import { Quality } from "./pages/Quality";
import { Procedures } from "./pages/Procedures";
import { Documentation } from "./pages/Documentation";
import { Statistics } from "./pages/Statistics";
import { Empty } from "./components/ui";
export function App() {
  const { user } = useAuth();
  return (
    <BrowserRouter>
      {!user ? (
        <Login />
      ) : (
        <UploadWorkspaceProvider key={user.id}>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route
                path="validation"
                element={
                  ["admin", "operator"].includes(user.role) ? (
                    <NewRun mode="validation" />
                  ) : (
                    <Navigate to="/references" replace />
                  )
                }
              />
              <Route path="procedures" element={<Procedures />} />
              <Route path="statistics" element={<Statistics />} />
              <Route path="documentation" element={<Documentation />} />
              <Route path="runs" element={<Runs />} />
              <Route
                path="runs/new"
                element={
                  ["admin", "operator"].includes(user.role) ? (
                    <NewRun />
                  ) : (
                    <Navigate to="/runs" replace />
                  )
                }
              />
              <Route path="runs/:id" element={<RunDetail />} />
              <Route path="review" element={<Review />} />
              <Route path="quality" element={<Quality />} />
              <Route path="results/:id" element={<ResultDetail />} />
              <Route path="references" element={<References />} />
              <Route path="rules" element={<Rules />} />
              <Route
                path="audit"
                element={<Navigate to="/documentation" replace />}
              />
              <Route
                path="*"
                element={
                  <Empty
                    title="Página no encontrada"
                    text="Usa la navegación principal para volver al espacio de trabajo."
                  />
                }
              />
            </Route>
          </Routes>
        </UploadWorkspaceProvider>
      )}
    </BrowserRouter>
  );
}
