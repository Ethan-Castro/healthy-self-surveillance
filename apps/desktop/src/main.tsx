import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import BubbleApp from "./BubbleApp";
import "./app.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element not found");
}

const params = new URLSearchParams(window.location.search);
const isBubble = params.get("mode") === "bubble";

document.documentElement.classList.toggle("bubble-mode", isBubble);
document.body.classList.toggle("bubble-mode", isBubble);

createRoot(root).render(
  <StrictMode>
    {isBubble ? <BubbleApp /> : <App />}
  </StrictMode>,
);
