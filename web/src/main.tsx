import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./cite-tokens.css";
import "./styles.css";
import "./review.css";
import "./manage.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
