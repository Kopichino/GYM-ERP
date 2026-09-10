const YOUTUBE_PATTERNS = [
  /youtu\.be\/([\w-]{11})/,
  /youtube\.com\/(?:watch\?v=|embed\/|shorts\/)([\w-]{11})/,
];

export function getYouTubeId(url: string): string | null {
  for (const pattern of YOUTUBE_PATTERNS) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export function getYouTubeThumbnail(url: string): string | null {
  const id = getYouTubeId(url);
  return id ? `https://img.youtube.com/vi/${id}/hqdefault.jpg` : null;
}
