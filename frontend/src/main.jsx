import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/pages.css";
import "./styles/smooth.css";

createRoot(document.getElementById("app")).render(<App />);
