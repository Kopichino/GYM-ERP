/**
 * How a person reads in a picker: their name, with the username alongside so two
 * people who share a name can still be told apart. An account with no name on
 * file falls back to the username alone.
 */
export function personLabel(person: { first_name?: string; last_name?: string; username: string }) {
  const name = `${person.first_name ?? ""} ${person.last_name ?? ""}`.trim();
  return name ? `${name} (${person.username})` : person.username;
}
