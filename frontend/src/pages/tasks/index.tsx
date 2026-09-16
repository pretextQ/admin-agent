import { Routes, Route } from "react-router-dom";
import TaskList from "./TaskList";
import TaskDetailPage from "./TaskDetail";

export default function TasksPage() {
  return (
    <Routes>
      <Route index element={<TaskList />} />
      <Route path=":id" element={<TaskDetailPage />} />
    </Routes>
  );
}
