import { useBranding } from "../hooks/useBranding";

/**
 * The gym's name, wordmark-styled.
 *
 * The two-tone treatment is the product's, not any one gym's, so it is applied
 * to whichever name is configured: the first word plain and the rest accented,
 * or -- for a single word like "IRONCORE" -- split down the middle, which is
 * exactly how the default renders. An uploaded logo replaces the text entirely.
 */
export default function BrandMark({ className = "" }: { className?: string }) {
  const branding = useBranding();
  const name = branding?.name || "IRONCORE";

  if (branding?.logo) {
    return <img src={branding.logo} alt={name} className={`h-8 w-auto ${className}`} />;
  }

  const space = name.indexOf(" ");
  const cut = space > 0 ? space : Math.ceil(name.length / 2);
  const head = name.slice(0, cut);
  const tail = name.slice(space > 0 ? cut + 1 : cut);

  return (
    <span className={className}>
      {head}
      {tail && <span className="text-[var(--color-accent)]">{space > 0 ? ` ${tail}` : tail}</span>}
    </span>
  );
}
