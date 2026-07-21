import "./App.css";
import HonestyPanel from "./components/HonestyPanel";
import MonitorMap from "./map/MonitorMap";

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>SinkScope</h1>
        <p className="subtitle">地盤沈下モニタリング＆下水道点検トリアージ ― Monitor</p>
      </header>

      <div className="app-body">
        <MonitorMap />
        <HonestyPanel />
      </div>
    </div>
  );
}

export default App;
