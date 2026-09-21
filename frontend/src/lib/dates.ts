/**
 * Calendar dates as the person looking at the screen would write them.
 *
 * `new Date().toISOString().slice(0, 10)` looks like the obvious way to get
 * "today" as YYYY-MM-DD, and it is wrong everywhere except UTC: it converts to
 * UTC first, so a gym in India (+5:30) gets *yesterday* for the whole morning,
 * and a gym in New York gets *tomorrow* every evening. That turned up as a
 * rota grid whose "today" marker sat on the wrong column, and it was quietly
 * doing the same thing to every date filter and form default in the app.
 *
 * These read the local parts instead, which is what a date input expects and
 * what the API's `DateField`s mean.
 */

/** A Date as its local YYYY-MM-DD. */
export function isoDate(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Today, locally. */
export function todayIso() {
  return isoDate(new Date());
}

/** `days` from now, locally. Negative goes backwards. */
export function isoDaysFromNow(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

/** The first of the current month, locally. */
export function monthStartIso() {
  const date = new Date();
  date.setDate(1);
  return isoDate(date);
}

/** Word for word what the API says about a backwards report window. */
export const END_BEFORE_START = "The end date is before the start date.";

/**
 * What is wrong with a From/To pair, or "" when nothing is -- including while
 * either is blank, since a blank end means "use the default". YYYY-MM-DD dates
 * compare correctly as text.
 */
export function dateRangeProblem(start: string, end: string) {
  return start && end && end < start ? END_BEFORE_START : "";
}

/** Monday of the week containing `date`, at local midnight. */
export function weekStart(date: Date) {
  const copy = new Date(date);
  // getDay() is Sunday-first; the rota, like the rest of the app, is not.
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7));
  copy.setHours(0, 0, 0, 0);
  return copy;
}
