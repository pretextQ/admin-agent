import { Outlet } from "react-router-dom";
import TabBar from "./TabBar";

export default function Layout() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "#fff",
      }}
    >
      <div style={{ flex: 1, overflow: "auto" }}>
        <Outlet />
      </div>
      <TabBar />
    </div>
  );
}
