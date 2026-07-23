import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import "./index.css";
import { App } from "./app.tsx";
import { ThemeProvider } from "./components/theme-provider.tsx";
import { TooltipProvider } from "./components/ui/tooltip.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="system" storageKey="usage-tracker-theme">
      <BrowserRouter>
        <TooltipProvider>
          <App />
        </TooltipProvider>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
