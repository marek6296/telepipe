"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { FileText, Loader2, RefreshCw } from "lucide-react";
import type { SocialMedia, SocialMessage } from "@/lib/social-types";

type RefreshPlayback = (mediaId:string) => Promise<string|null|undefined>;
export function MessageMedia({message,refreshPlayback}: {message:SocialMessage;refreshPlayback?:RefreshPlayback}) {
  if (message.media?.length) return <div className="mb-2 space-y-3">{message.media.map(media => <Media key={media.id} media={media} refreshPlayback={refreshPlayback} />)}</div>;
  const attachment = message.attachment;
  if (!attachment) return null;
  return <div className="mb-2">{attachment.url && ["image","photo"].includes(attachment.kind)
    ? <a href={attachment.url} target="_blank" rel="noopener noreferrer"><Image src={attachment.url} alt="Message attachment" width={480} height={360} unoptimized className="max-h-64 w-auto max-w-full rounded-md object-contain" /></a>
    : attachment.url && ["audio","voice"].includes(attachment.kind)
      ? <audio controls preload="none" src={attachment.url} className="w-full min-w-0 max-w-full" aria-label="Audio message" />
      : attachment.url && attachment.kind === "video"
        ? <video controls playsInline preload="none" src={attachment.url} className="max-h-64 max-w-full rounded-md" aria-label="Video message" />
        : <span className="inline-flex items-center gap-1.5 text-[11px] text-[var(--app-text-3)]"><FileText className="h-3 w-3" />{attachment.url ? <a href={attachment.url} target="_blank" rel="noopener noreferrer" className="underline">Open {attachment.kind} attachment</a> : `${attachment.kind} attachment · preview unavailable`}</span>}</div>;
}

function Media({media,refreshPlayback}: {media:SocialMedia;refreshPlayback?:RefreshPlayback}) {
  // Signing may produce a new URL on every poll. Keep the loaded source stable
  // while playing; use the latest signed URL only when retrying an expired file.
  const [source, setSource] = useState(media.playbackUrl);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const player = useRef<HTMLMediaElement | null>(null);
  const resumeAt = useRef(0);
  function restorePosition() {
    const element = player.current;
    if (element && resumeAt.current > 0) {
      try { element.currentTime = Math.min(resumeAt.current, Number.isFinite(element.duration) ? element.duration : resumeAt.current); } catch { /* Some streams cannot seek. */ }
      resumeAt.current = 0;
    }
  }
  if (!source && media.playbackUrl) setSource(media.playbackUrl);
  const loading = media.status === "pending" || media.status === "processing";
  return <section className="min-w-0 space-y-2" aria-label={`${media.kind} attachment`}>
    <div className="flex items-center justify-between gap-3 text-[10px] text-[var(--app-text-3)]"><span className="capitalize">{media.kind === "audio" ? "Voice / audio" : media.kind}</span>{media.durationSeconds !== null && <span>{Math.floor(media.durationSeconds / 60)}:{String(Math.floor(media.durationSeconds % 60)).padStart(2,"0")}</span>}</div>
    {source ? <>
      {media.kind === "audio" ? <audio ref={element => { player.current = element; }} onLoadedMetadata={restorePosition} key={attempt} controls preload="none" src={source} onError={() => setFailed(true)} className="w-full min-w-0 max-w-full" aria-label="Audio message" />
        : media.kind === "video" ? <video ref={element => { player.current = element; }} onLoadedMetadata={restorePosition} key={attempt} controls playsInline preload="none" src={source} onError={() => setFailed(true)} className="max-h-72 w-full rounded-md bg-black" aria-label="Video message" />
          : media.kind === "image" ? <a href={media.playbackUrl || source} target="_blank" rel="noopener noreferrer"><Image key={attempt} src={source} onError={() => setFailed(true)} alt="Message attachment" width={480} height={360} unoptimized className="max-h-72 w-auto max-w-full rounded-md object-contain" /></a>
            : <a href={media.playbackUrl || source} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 underline underline-offset-2"><FileText className="h-3.5 w-3.5" />Open attachment</a>}
      {failed && <div role="status" className="text-[11px] text-[var(--app-text-3)]"><p>Playback could not load. Refresh the conversation if retry does not help.</p><button type="button" disabled={retrying} onClick={async () => {
        resumeAt.current = player.current?.currentTime || 0; setRetrying(true);
        try { const renewed = await refreshPlayback?.(media.id); setSource(renewed || media.playbackUrl); setFailed(false); setAttempt(previous => previous + 1); }
        finally { setRetrying(false); }
      }} className="mt-1 inline-flex min-h-9 items-center gap-1.5 underline underline-offset-2"><RefreshCw className="h-3 w-3" />Retry playback</button></div>}
    </> : <p className="rounded-md border border-[var(--app-border-strong)] px-3 py-2 text-[11px] text-[var(--app-text-3)]">{loading ? "Preparing this attachment…" : "Playback unavailable for this attachment."}</p>}
    {loading && <p role="status" className="flex items-center gap-1.5 text-[10px] text-[var(--app-text-3)]"><Loader2 className="h-3 w-3 animate-spin" />{media.status === "pending" ? "Waiting for media processing" : "Analyzing attachment…"}</p>}
    {(media.status === "failed" || media.status === "unavailable") && <p className="text-[11px] text-[var(--app-text-3)]">{media.error || (media.status === "failed" ? "Media analysis could not be completed." : "This attachment is no longer available.")}</p>}
    {media.kind === "video" && media.description && <Analysis label="Video description · sampled frames" text={media.description} />}
    {(media.kind === "audio" || media.kind === "video") && media.transcript && <Analysis label="Transcript" text={media.transcript} />}
    {(media.kind === "audio" || media.kind === "video") && media.status === "ready" && !media.transcript && <p className="text-[10px] text-[var(--app-text-4)]">No transcript available.</p>}
  </section>;
}
function Analysis({label,text}: {label:string; text:string}) {
  return <div className="border-l-2 border-[var(--app-border-strong)] pl-2.5"><h4 className="text-[9px] font-medium uppercase tracking-wider text-[var(--app-text-4)]">{label}</h4><p className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-5">{text}</p></div>;
}
