/** Word for word what the API says about a number that cannot be dialled. */
export const NOT_A_PHONE = "That doesn't look like a phone number.";

/**
 * Whether `value` has enough digits to dial: at least 7, with spaces, dashes,
 * brackets or a leading + around them. The same rule the server holds, so the
 * form and the API never disagree about a number.
 */
export function looksDialable(value: string) {
  return (value.match(/\d/g) ?? []).length >= 7;
}
