import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchBrandingAdmin, saveBranding, type BrandingAdmin } from "../../api/branding";
import {
  Button,
  Card,
  ErrorState,
  ErrorText,
  Input,
  Select,
  LoadingState,
  Textarea,
} from "../../components/ui";
import { railColor } from "../../lib/theme";

/** The faces a gym may pick, each previewed in itself. Kept in step with
 *  `branding.models.DisplayFont`; the server rejects anything not on the list. */
const DISPLAY_FONTS = [
  { value: "Bebas Neue", label: "Bebas Neue - condensed, athletic (default)" },
  { value: "Anton", label: "Anton - heavy and blunt" },
  { value: "Oswald", label: "Oswald - condensed, quieter" },
  { value: "Archivo Black", label: "Archivo Black - very heavy" },
  { value: "Teko", label: "Teko - squared, sporty" },
];

/**
 * Pull in every option while this screen is open.
 *
 * `useBranding` loads only the face a gym has actually saved, which is right
 * everywhere else -- four unused fonts on every page load would be waste. But
 * a picker that previews four faces the browser has not fetched shows all of
 * them in the fallback, which makes the choice meaningless. So they are loaded
 * here and nowhere else.
 */
function usePreviewFonts() {
  useEffect(() => {
    const links = DISPLAY_FONTS.map((font) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${font.value.replace(
        / /g,
        "+",
      )}&display=swap`;
      document.head.appendChild(link);
      return link;
    });
    return () => links.forEach((link) => link.remove());
  }, []);
}

const BLANK = {
  name: "",
  tagline: "",
  accent: "#ff3d5a",
  accent_2: "#ffb020",
  display_font: "Bebas Neue",
  phone: "",
  email: "",
  address: "",
  website: "",
  instagram: "",
  gstin: "",
  state: "",
};

/**
 * The form itself, kept separate so the current identity can seed it through
 * `useState` rather than an effect: the parent remounts this on a `key` when a
 * different identity arrives, which is what makes "server data as the initial
 * value" honest instead of a copy that has to be re-synchronised.
 */
function BrandingForm({ current }: { current?: BrandingAdmin }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(
    current
      ? {
          name: current.name,
          tagline: current.tagline,
          accent: current.accent,
          accent_2: current.accent_2,
          display_font: current.display_font,
          phone: current.phone,
          email: current.email,
          address: current.address,
          website: current.website,
          instagram: current.instagram,
          gstin: current.gstin,
          state: current.state,
        }
      : BLANK
  );
  const [logo, setLogo] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () => {
      const body = new FormData();
      Object.entries(form).forEach(([key, value]) => body.append(key, value));
      if (logo) body.append("logo", logo);
      return saveBranding(body);
    },
    onSuccess: () => {
      setError("");
      setSaved(true);
      setLogo(null);
      // The palette is applied from this query, so refreshing it repaints the
      // portal immediately rather than on the next reload.
      queryClient.invalidateQueries({ queryKey: ["branding"] });
    },
    onError: (err: { response?: { data?: Record<string, string[]> } }) => {
      const first = err.response?.data && Object.entries(err.response.data)[0];
      setSaved(false);
      setError(first ? `${first[0]}: ${first[1]}` : "Could not save that.");
    },
  });

  usePreviewFonts();

  function field(key: keyof typeof BLANK) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setSaved(false);
      setForm((f) => ({ ...f, [key]: e.target.value }));
    };
  }

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(0)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Gym identity
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          This is the name and colours the whole system uses — the member portal, the login
          screen, GST invoices and reminder emails. Saving replaces the current identity; the
          previous one is kept, not deleted.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Input placeholder="Gym name" value={form.name} onChange={field("name")} />
          <Input placeholder="Tagline (optional)" value={form.tagline} onChange={field("tagline")} />
          <div className="sm:col-span-2">
            <label
              htmlFor="branding-font"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              Headline font
            </label>
            <Select
              id="branding-font"
              value={form.display_font}
              onChange={(e) => setForm((f) => ({ ...f, display_font: e.target.value }))}
            >
              {DISPLAY_FONTS.map((font) => (
                <option key={font.value} value={font.value}>
                  {font.label}
                </option>
              ))}
            </Select>
            <p
              className="mt-2 text-3xl uppercase tracking-wide text-[var(--color-text)]"
              style={{ fontFamily: `"${form.display_font}", "Inter", sans-serif` }}
            >
              {form.name || "Your gym name"}
            </p>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              Headings only. Body text stays Inter so every screen stays readable.
            </p>
          </div>

          <label className="text-xs text-[var(--color-text-muted)]">
            Primary colour
            <div className="mt-1 flex gap-2">
              <input
                type="color"
                value={form.accent}
                onChange={field("accent")}
                className="h-10 w-12 cursor-pointer rounded-md border border-[var(--color-border)] bg-transparent"
              />
              <Input value={form.accent} onChange={field("accent")} />
            </div>
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Secondary colour
            <div className="mt-1 flex gap-2">
              <input
                type="color"
                value={form.accent_2}
                onChange={field("accent_2")}
                className="h-10 w-12 cursor-pointer rounded-md border border-[var(--color-border)] bg-transparent"
              />
              <Input value={form.accent_2} onChange={field("accent_2")} />
            </div>
          </label>
        </div>

        <div className="mt-3">
          <label className="text-xs text-[var(--color-text-muted)]">
            Logo
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setLogo(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm text-[var(--color-text-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--color-border)] file:bg-[var(--color-surface-2)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--color-text)]"
            />
          </label>
          {current?.logo && !logo && (
            <img
              src={current.logo}
              alt="Current logo"
              className="mt-2 h-12 rounded-md bg-[var(--color-surface-2)] p-1"
            />
          )}
        </div>
      </Card>

      <Card accent={railColor(2)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Contact and tax details
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          The address and GSTIN are printed on invoices. The state decides whether a sale is
          split into CGST + SGST or charged as IGST, so it has to match your registration.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input placeholder="Phone" value={form.phone} onChange={field("phone")} />
          <Input placeholder="Email" value={form.email} onChange={field("email")} />
          <Input placeholder="Website" value={form.website} onChange={field("website")} />
          <Input placeholder="Instagram handle" value={form.instagram} onChange={field("instagram")} />
          <Input placeholder="GSTIN" value={form.gstin} onChange={field("gstin")} />
          <Input placeholder="State (e.g. Maharashtra)" value={form.state} onChange={field("state")} />
        </div>
        <Textarea
          rows={3}
          placeholder="Address, as it should appear on an invoice"
          value={form.address}
          onChange={field("address")}
          className="mt-3"
        />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={() => save.mutate()} disabled={!form.name || save.isPending}>
            {save.isPending ? "Saving..." : "Save identity"}
          </Button>
          {saved && (
            <span className="text-sm" style={{ color: "#22c55e" }}>
              Saved — the new colours are live.
            </span>
          )}
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>
    </div>
  );
}

export default function AdminBrandingPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["branding", "admin"],
    queryFn: fetchBrandingAdmin,
  });

  if (isLoading) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }
  if (isError) {
    return (
      <Card>
        <ErrorState />
      </Card>
    );
  }

  const current = data?.find((b) => b.is_active);
  // Remounting on the identity discards a half-typed form only when the thing
  // being edited has actually changed underneath.
  return <BrandingForm key={current?.updated_at ?? "new"} current={current} />;
}
