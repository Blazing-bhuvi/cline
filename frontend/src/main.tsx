import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// NOTE: StrictMode is intentionally NOT used here. In development StrictMode
// double-invokes effects, which calls getUserMedia() twice in quick succession.
// The browser then aborts one request ("...aborted by the user agent...") while
// the other leaves the camera running even though the UI reports an error.
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);

