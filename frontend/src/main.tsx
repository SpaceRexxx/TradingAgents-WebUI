import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import App from "./App";
import ConfigPage from "./pages/ConfigPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import HistoryPage from "./pages/HistoryPage";
import "./styles/tokens.css";
import "./styles/components.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/analysis" replace /> },
      { path: "analysis", element: <div data-testid="placeholder-analysis" /> },
      { path: "history", element: <HistoryPage /> },
      { path: "config", element: <ConfigPage /> },
      { path: "diagnostics", element: <DiagnosticsPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
