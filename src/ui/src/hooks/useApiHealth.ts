import { useEffect, useState } from "react";
import { agnesApi, getMode, onModeChange, setMode } from "@/lib/agnesApi";
import { useAgnesStore } from "@/store/agnesStore";

// Polls the Agnes API and toggles a global online/offline indicator.
// Auto-flips into demo mode when offline so the UI stays interactive.
export function useApiHealth() {
  const setApiOnline = useAgnesStore((s) => s.setApiOnline);
  const apiOnline = useAgnesStore((s) => s.apiOnline);
  const [mode, setLocalMode] = useState(getMode());

  useEffect(() => {
    let cancelled = false;
    let timer: number;
    const check = async () => {
      try {
        await agnesApi.health();
        if (!cancelled) {
          setApiOnline(true);
          setMode("live");
        }
      } catch {
        if (!cancelled) {
          setApiOnline(false);
          setMode("demo");
        }
      }
    };
    void check();
    timer = window.setInterval(check, 15000);
    const off = onModeChange(setLocalMode);
    return () => { cancelled = true; window.clearInterval(timer); off(); };
  }, [setApiOnline]);

  return { apiOnline, mode, toggleMode: () => setMode(getMode() === "live" ? "demo" : "live") };
}
