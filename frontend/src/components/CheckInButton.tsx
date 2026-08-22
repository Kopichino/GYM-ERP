import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { checkIn, checkOut, fetchCurrentCheckIn } from "../api/attendance";
import { Button, Card } from "./ui";

function formatElapsed(sinceIso: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(sinceIso).getTime()) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function CheckInButton() {
  const queryClient = useQueryClient();
  const { data: current, isLoading } = useQuery({
    queryKey: ["attendance", "current"],
    queryFn: fetchCurrentCheckIn,
  });
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!current) return;
    const interval = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(interval);
  }, [current]);

  const checkInMutation = useMutation({
    mutationFn: checkIn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["attendance"] }),
  });
  const checkOutMutation = useMutation({
    mutationFn: checkOut,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["attendance"] }),
  });

  const busy = checkInMutation.isPending || checkOutMutation.isPending || isLoading;

  return (
    <Card className="flex flex-col items-center gap-4 py-10 text-center">
      {current ? (
        <>
          <p className="text-sm uppercase tracking-wide text-[var(--color-text-muted)]">Checked in since</p>
          <p className="text-lg text-[var(--color-text)]">
            {new Date(current.check_in_time).toLocaleTimeString()}
          </p>
          <p className="font-mono text-4xl font-bold text-[var(--color-accent)]">
            {formatElapsed(current.check_in_time)}
          </p>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => checkOutMutation.mutate()}
            className="w-48 py-3 text-base"
          >
            {checkOutMutation.isPending ? "Checking out..." : "Check Out"}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm uppercase tracking-wide text-[var(--color-text-muted)]">Status</p>
          <p className="text-lg text-[var(--color-text)]">Not checked in</p>
          <Button
            disabled={busy}
            onClick={() => checkInMutation.mutate()}
            className="w-48 py-3 text-base"
          >
            {checkInMutation.isPending ? "Checking in..." : "Check In"}
          </Button>
        </>
      )}
      {(checkInMutation.isError || checkOutMutation.isError) && (
        <p className="text-sm text-red-400">Something went wrong -- try again.</p>
      )}
    </Card>
  );
}
