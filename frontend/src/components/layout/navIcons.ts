/**
 * 24x24 stroke paths for portal navigation, drawn with a shared <svg> wrapper.
 *
 * One set for all three portals, so a destination they share -- Announcements,
 * Gallery, Schedule -- wears the same icon whichever portal you reach it from.
 */
export const ICONS = {
  gauge: "M12 21a9 9 0 1 1 9-9M12 12l5-3M12 21h9",
  members: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M12 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  trainers: "M12 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM8.6 13.6 7 22l5-3 5 3-1.6-8.4",
  phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.4-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2Z",
  share: "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8.6 13.5l6.8 4M15.4 6.5l-6.8 4",
  heartbeat: "M22 12h-4l-3 8-4-16-3 8H2",
  medal: "M12 15a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM8.2 13.8 7 22l5-2.5L17 22l-1.2-8.2",
  roster: "M8 2v4M16 2v4M3 10h18M5 6h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2ZM8 14h3M8 18h6",
  ticket: "M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V8ZM14 6v2M14 11v2M14 16v2",
  speech: "M12 2a9 9 0 0 1 9 9c0 5-4 9-9 9a9.3 9.3 0 0 1-3.4-.6L3 21l1.4-4.2A8.9 8.9 0 0 1 3 11a9 9 0 0 1 9-9ZM8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01",
  chat: "M21 11.5A8.4 8.4 0 0 1 12 20a8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z",
  card: "M2 7h20v11a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7ZM2 11h20",
  layers: "M12 2 2 7l10 5 10-5-10-5ZM2 17l10 5 10-5M2 12l10 5 10-5",
  tag: "M20.6 13.4 12 22l-9-9V4h9l8.6 8.6a1.4 1.4 0 0 1 0 2ZM7.5 7.5h.01",
  receipt: "M4 3h16v18l-3-2-3 2-3-2-3 2V3ZM8 8h8M8 12h6",
  percent: "M19 5 5 19M6.5 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM17.5 20a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  chart: "M3 3v18h18M8 17V9M13 17V5M18 17v-6",
  upload: "M12 3v12M8 7l4-4 4 4M3 17v2a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2",
  device: "M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3M6 6h12v12H6zM10 10h4v4h-4z",
  qr: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM19 19h2v2h-2z",
  megaphone: "M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1ZM16 8a5 5 0 0 1 0 8",
  person: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  calendar: "M3 5h18v16H3zM3 9h18M8 3v4M16 3v4",
  image: "M3 4h18v16H3zM3 16l5-5 4 4 3-3 6 6M8.5 8.5h.01",
  form: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6ZM14 2v6h6M8 13h8M8 17h5",
  palette:
    "M12 3a9 9 0 1 0 0 18 2 2 0 0 0 1.6-3.2 2 2 0 0 1 1.6-3.2H18a3 3 0 0 0 3-3 9 9 0 0 0-9-9ZM7.5 11h.01M10.5 7.5h.01M14 7.5h.01",
  // Member and trainer destinations.
  dumbbell: "M6.5 6.5v11M17.5 6.5v11M3.5 9v6M20.5 9v6M6.5 12h11",
  bowl: "M4 12h16a8 8 0 0 1-16 0ZM8 8c0-1 1-1.5 1-2.5M12 8c0-1 1-1.5 1-2.5M16 8c0-1 1-1.5 1-2.5",
  library: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15ZM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  stopwatch: "M12 22a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM12 10v4l2 2M9 2h6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21a8 8 0 0 1 16 0",
} as const;
