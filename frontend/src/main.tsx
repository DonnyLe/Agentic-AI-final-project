import "@/styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { DesignPreview } from "@/design/DesignPreview.tsx";

const root = document.getElementById("root");

if (root) {
  createRoot(root).render(
    <StrictMode>
      <DesignPreview />
    </StrictMode>,
  );
}
