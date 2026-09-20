import { Navigate, Route, Routes } from "react-router-dom";
import HomeHub from "./pages/HomeHub";
import AskConsole from "./pages/AskConsole";
import PlaceholderPage from "./pages/PlaceholderPage";
import WorkspaceList from "./pages/workspaces/WorkspaceList";
import WorkspaceTrash from "./pages/workspaces/WorkspaceTrash";
import WorkspaceDetail from "./pages/workspaces/WorkspaceDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeHub />} />
      <Route path="/ask" element={<AskConsole />} />
      <Route path="/workspaces" element={<WorkspaceList />} />
      <Route path="/workspaces/trash" element={<WorkspaceTrash />} />
      <Route path="/workspaces/:id" element={<WorkspaceDetail />} />
      <Route
        path="/agents"
        element={
          <PlaceholderPage
            title="ایجنت‌ها"
            code="AGT"
            blurb="مدیریت ایجنت‌ها بعداً اینجا می‌آید."
          />
        }
      />
      <Route
        path="/api-mcp"
        element={
          <PlaceholderPage
            title="API & MCP"
            code="API"
            blurb="قرارداد API و اتصال MCP بعداً اینجا می‌آید."
          />
        }
      />
      <Route
        path="/pipeline"
        element={
          <PlaceholderPage
            title="Pipeline"
            code="PIP"
            blurb="نمای pipeline ایندکس/پردازش بعداً اینجا می‌آید."
          />
        }
      />
      <Route
        path="/guide"
        element={
          <PlaceholderPage
            title="راهنما"
            code="DOC"
            blurb="راهنمای محصول و اپراتور بعداً اینجا می‌آید."
          />
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
