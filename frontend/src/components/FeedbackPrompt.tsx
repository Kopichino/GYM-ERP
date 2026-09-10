import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchPendingPrompts, submitResponse } from "../api/feedback";
import { Button, Card, Textarea } from "./ui";

const SCORES = Array.from({ length: 11 }, (_, i) => i);

/** The NPS bands, coloured so the scale reads as a gradient rather than eleven
 *  identical buttons — and so the member can see which end is which. */
function scoreColor(score: number) {
  if (score >= 9) return "#22c55e";
  if (score >= 7) return "#ffb020";
  return "#ff3d5a";
}

/**
 * The one question a member gets asked after a visit.
 *
 * Renders nothing at all unless something is actually pending, so a member who
 * has already answered never sees an empty "no surveys" card taking up the top
 * of their dashboard.
 */
export default function FeedbackPrompt() {
  const queryClient = useQueryClient();
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);

  const { data: prompts } = useQuery({
    queryKey: ["feedback", "pending"],
    queryFn: fetchPendingPrompts,
  });

  const prompt = prompts?.[0];

  const send = useMutation({
    mutationFn: () =>
      submitResponse({
        survey: prompt!.survey.id,
        score: score!,
        comment,
        visit: prompt!.visit,
        pt_session: prompt!.pt_session,
      }),
    onSuccess: () => {
      setDone(true);
      queryClient.invalidateQueries({ queryKey: ["feedback"] });
    },
    // A double-tapped Send comes back 409; the answer landed, so say thank you
    // rather than showing the member an error for succeeding.
    onError: () => setDone(true),
  });

  // Checked before the empty case: sending invalidates the pending query, so
  // by the time the answer lands there is no prompt left and the thank-you
  // would never be seen if `!prompt` returned first.
  if (done) {
    return (
      <Card accent="#22c55e">
        <p className="text-sm text-[var(--color-text)]">
          Thanks — that goes straight to the gym.
        </p>
      </Card>
    );
  }

  if (!prompt) return null;

  return (
    <Card accent="#a855f7">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {prompt.survey.title}
      </h2>
      <p className="mt-1 text-sm text-[var(--color-text)]">{prompt.survey.question}</p>

      {/* Eleven fixed-width buttons wrap in a narrow column, which puts the
          10 on a line of its own and breaks the scale in half. A grid of
          eleven equal columns keeps it one row at any width. */}
      <div className="mt-3 grid grid-cols-11 gap-1">
        {SCORES.map((value) => {
          const picked = score === value;
          return (
            <button
              key={value}
              type="button"
              aria-label={`Score ${value} out of 10`}
              aria-pressed={picked}
              onClick={() => setScore(value)}
              className="aspect-square w-full min-w-0 rounded-md border text-xs font-semibold transition-transform hover:scale-110"
              style={{
                borderColor: picked ? scoreColor(value) : "var(--color-border)",
                background: picked
                  ? scoreColor(value)
                  : `color-mix(in srgb, ${scoreColor(value)} 12%, transparent)`,
                color: picked ? "var(--color-on-accent)" : "var(--color-text)",
              }}
            >
              {value}
            </button>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-[var(--color-text-muted)]">
        <span>Not likely</span>
        <span>Very likely</span>
      </div>

      {score !== null && (
        <>
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            placeholder={
              score <= 6
                ? "What would have made it better? (optional)"
                : "Anything you'd like to add? (optional)"
            }
            className="mt-3"
          />
          <Button
            onClick={() => send.mutate()}
            disabled={send.isPending}
            className="mt-3"
          >
            Send
          </Button>
        </>
      )}
    </Card>
  );
}
