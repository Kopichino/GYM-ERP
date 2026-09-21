import { useCallback, useRef } from "react";

/**
 * Lets a form submit only once while its save is still in flight.
 *
 * Disabling the button on `mutation.isPending` is not enough by itself: the flag
 * only reaches the button after React re-renders, and a double click delivers
 * both clicks before that -- so both went to the server. A ref changes the
 * moment the first submit starts, which is what turns the second one away.
 *
 * It is released when the save settles, success or failure, so a refused save
 * leaves the form usable rather than stuck.
 *
 *   const submitOnce = useSubmitOnce();
 *   submitOnce((settled) => mutation.mutate(undefined, { onSettled: settled }));
 */
export function useSubmitOnce() {
  const inFlight = useRef(false);

  return useCallback((start: (settled: () => void) => void) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const settled = () => {
      inFlight.current = false;
    };
    try {
      start(settled);
    } catch (error) {
      settled();
      throw error;
    }
  }, []);
}
