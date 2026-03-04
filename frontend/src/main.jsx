// Suppress moment.defineLocale deprecation from TradingView widget (third-party bundle)
const _warn = console.warn;
console.warn = (...args) => {
  if (args[0]?.includes?.("defineLocale") && args[0]?.includes?.("updateLocale")) return;
  _warn.apply(console, args);
};

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
