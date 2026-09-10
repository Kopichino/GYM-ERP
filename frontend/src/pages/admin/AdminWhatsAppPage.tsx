import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  fetchMessages,
  fetchWhatsAppStatus,
  sendMessage,
  type WhatsAppMessage,
} from "../../api/messaging";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
} from "../../components/ui";
import { railColor } from "../../lib/theme";

/** Groups the log into one thread per number, newest thread first. */
function threadsFrom(messages: WhatsAppMessage[]) {
  const byPhone = new Map<string, WhatsAppMessage[]>();
  for (const message of messages) {
    const existing = byPhone.get(message.phone);
    if (existing) existing.push(message);
    else byPhone.set(message.phone, [message]);
  }
  return [...byPhone.entries()].map(([phone, thread]) => ({
    phone,
    // The API returns newest first; a conversation reads oldest first.
    messages: [...thread].reverse(),
    latest: thread[0],
    who: thread.find((m) => m.username)?.username ?? null,
  }));
}

function Bubble({ message }: { message: WhatsAppMessage }) {
  const outbound = message.direction === "out";
  return (
    <div className={`flex ${outbound ? "justify-end" : "justify-start"}`}>
      <div
        className="max-w-[80%] rounded-lg px-3 py-2 text-sm"
        style={{
          background: outbound ? "var(--color-accent)" : "var(--color-surface-2)",
          color: outbound ? "#fff" : "var(--color-text)",
        }}
      >
        <p className="whitespace-pre-wrap">{message.body}</p>
        <p
          className="mt-1 text-[10px] opacity-70"
          style={{ color: outbound ? "#fff" : "var(--color-text-muted)" }}
        >
          {new Date(message.created_at).toLocaleString()}
          {message.is_automated && " · assistant"}
          {message.status === "failed" && ` · failed: ${message.error}`}
        </p>
      </div>
    </div>
  );
}

export default function AdminWhatsAppPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");

  const { data: status } = useQuery({
    queryKey: ["whatsapp", "status"],
    queryFn: fetchWhatsAppStatus,
  });
  const { data: messages, isLoading, isError } = useQuery({
    queryKey: ["whatsapp", "messages"],
    queryFn: () => fetchMessages(),
    // The assistant answers on its own, so the log moves without anyone here
    // doing anything.
    refetchInterval: 20_000,
  });

  const threads = useMemo(() => threadsFrom(messages ?? []), [messages]);
  const thread = threads.find((t) => t.phone === selected) ?? threads[0];

  const post = useMutation({
    mutationFn: () => sendMessage(thread!.phone, reply),
    onSuccess: () => {
      setReply("");
      setError("");
      queryClient.invalidateQueries({ queryKey: ["whatsapp"] });
    },
    onError: () => setError("Could not send that. Check the WhatsApp connection."),
  });

  return (
    <div className="flex flex-col gap-6">
      {status && !status.enabled && (
        <Card accent="#ffb020">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            WhatsApp isn't connected
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Set <code>WHATSAPP_TOKEN</code>, <code>WHATSAPP_PHONE_NUMBER_ID</code>,{" "}
            <code>WHATSAPP_VERIFY_TOKEN</code> and <code>WHATSAPP_APP_SECRET</code> from your Meta
            Business account, then point Meta's webhook at{" "}
            <code>/api/whatsapp/webhook/</code>. Until then nothing is sent and the assistant
            never replies — messages here would only be recorded as failed.
          </p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
        <Card accent={railColor(0)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {threads.length} conversation{threads.length === 1 ? "" : "s"}
          </h2>
          {isLoading ? (
            <LoadingState />
          ) : isError ? (
            <ErrorState />
          ) : !threads.length ? (
            <EmptyState>Nothing yet. Member messages appear here as they arrive.</EmptyState>
          ) : (
            <ul className="flex flex-col">
              {threads.map((t) => (
                <li key={t.phone}>
                  <button
                    onClick={() => setSelected(t.phone)}
                    className={`w-full border-b border-[var(--color-border)] py-2 text-left last:border-none ${
                      thread?.phone === t.phone ? "text-[var(--color-text)]" : ""
                    }`}
                  >
                    <span className="block text-sm text-[var(--color-text)]">
                      {t.who ?? t.phone}
                    </span>
                    <span className="block truncate text-xs text-[var(--color-text-muted)]">
                      {t.latest.body}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card accent={railColor(2)}>
          {!thread ? (
            <EmptyState>Pick a conversation to read it.</EmptyState>
          ) : (
            <>
              <div className="mb-3 flex items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {thread.who ?? "Unknown number"}
                </h2>
                <span className="text-xs text-[var(--color-text-muted)]">+{thread.phone}</span>
              </div>

              <div className="no-scrollbar flex max-h-[420px] flex-col gap-2 overflow-y-auto pr-1">
                {thread.messages.map((m) => (
                  <Bubble key={m.id} message={m} />
                ))}
              </div>

              <div className="mt-4 flex gap-2 border-t border-[var(--color-border)] pt-3">
                <Input
                  placeholder="Reply as the front desk"
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  className="flex-1"
                />
                <Button
                  onClick={() => post.mutate()}
                  disabled={!reply || post.isPending || !status?.enabled}
                >
                  {post.isPending ? "Sending..." : "Send"}
                </Button>
              </div>
              <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                A free-text reply only reaches the member within 24 hours of their last message —
                that is WhatsApp's rule, not ours.
              </p>
              <ErrorText>{error}</ErrorText>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
