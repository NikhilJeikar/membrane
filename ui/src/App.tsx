import AppShell from "./components/AppShell";
import { ToastProvider } from "./components/ui/Toast";

export default function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  );
}
