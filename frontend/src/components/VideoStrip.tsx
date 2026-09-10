import type { ExerciseVideo } from "../api/workouts";
import { getYouTubeThumbnail } from "../lib/youtube";

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path fill="currentColor" d="M8 5.5v13l11-6.5-11-6.5Z" />
    </svg>
  );
}

function VideoCard({ video }: { video: ExerciseVideo }) {
  const thumb = getYouTubeThumbnail(video.url);
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative block h-24 w-40 shrink-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] transition-transform hover:-translate-y-0.5 hover:border-[var(--color-accent)]"
    >
      {thumb ? (
        <img src={thumb} alt={video.title || "Tutorial video"} className="h-full w-full object-cover opacity-80 transition-opacity group-hover:opacity-100" />
      ) : (
        <div className="flex h-full w-full items-center justify-center px-2 text-center text-[11px] text-[var(--color-text-muted)]">
          {video.title || "Watch tutorial"}
        </div>
      )}
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 transition-opacity group-hover:opacity-100">
        <PlayIcon className="h-8 w-8 text-white drop-shadow" />
      </div>
      {video.title && (
        <p className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-2 pb-1 pt-3 text-left text-[11px] font-medium text-white">
          {video.title}
        </p>
      )}
    </a>
  );
}

export default function VideoStrip({ videos }: { videos: ExerciseVideo[] }) {
  if (videos.length === 0) {
    return <p className="text-sm text-[var(--color-text-muted)]">Tutorials coming soon.</p>;
  }
  return (
    <div className="scroll-thin flex gap-3 overflow-x-auto pb-1">
      {videos.map((video) => (
        <VideoCard key={video.id} video={video} />
      ))}
    </div>
  );
}
