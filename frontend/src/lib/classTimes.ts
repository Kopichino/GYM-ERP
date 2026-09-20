/** Word for word what the API says, so the form and the server never disagree. */
export const END_BEFORE_START = "A class has to end after it starts.";

/**
 * What is wrong with a class's start and end, or "" when nothing is -- including
 * while either is still blank, so the form does not complain before it is filled.
 *
 * A class is one date, so the end must be later than the start on that day; an
 * equal start and end is refused too. Time inputs give "HH:MM", which compares
 * correctly as text.
 */
export function classTimeProblem(start: string, end: string) {
  return start && end && end <= start ? END_BEFORE_START : "";
}
