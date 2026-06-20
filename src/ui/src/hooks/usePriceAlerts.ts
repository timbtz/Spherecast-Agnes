import { useQuery } from "@tanstack/react-query";
import { agnesApi } from "@/lib/agnesApi";

export function usePriceAlertCount() {
  return useQuery({
    queryKey: ["alert-count"],
    queryFn: () => agnesApi.alertCount(),
    refetchInterval: 60_000,
  });
}
