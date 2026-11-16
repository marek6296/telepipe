"use client";

import { useState, useTransition } from "react";
import Image from "next/image";
import { manageInstagramAction } from "@/app/app/m/[id]/instagram/settings/actions";
import { Card, CardHeader } from "@/components/app/ui";

export type SharedIdentity = {id: string; platform: string; external_id: string; username: string; display_name: string; status: string; candidate_id: string | null};
export type QueueAction = {id: string; kind: string; igsid: string; state: string; due_at: string; reason: string; text: string};
export type ApprovedPhoto = {id: number; url: string; caption: string; instagram_approved: boolean};
const name = (row: SharedIdentity) => `${row.platform}: ${row.username || row.display_name || row.external_id}`;

export function ConversationControls({modelId, identities, queue, takeovers, photos, syncStatus, testUntil, circuitUntil}: {
  modelId: string; identities: SharedIdentity[]; queue: QueueAction[];
  takeovers: {igsid: string; username: string}[]; photos: ApprovedPhoto[];
  syncStatus: string; testUntil: string | null; circuitUntil: string | null;
}) {
  const [pending, start] = useTransition();
  const [notice, setNotice] = useState("");
  const [testUser, setTestUser] = useState("dony.donoval");
  const [photoId, setPhotoId] = useState(String(photos.find(p => p.instagram_approved)?.id ?? ""));
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const run = (operation: string, value: string, other = "") => start(async () => {
    try {
      const result = await manageInstagramAction(modelId, operation, value, other);
      setNotice(result.error || result.message || "Saved.");
    } catch { setNotice("Could not save. Refresh and try again."); }
  });
  const chosen = photos.find(p => String(p.id) === photoId);
  const candidates = identities.filter(i => i.candidate_id && ["candidate", "recognized", "verified"].includes(i.status));
  const button = "app-button-secondary disabled:opacity-50";
  return <div className="mt-6 space-y-5">
    {notice && <p role="status" className="text-sm">{notice}</p>}
    <Card>
      <CardHeader title="Conversation continuity" description="Matching names and recent invitations can recognize a likely visitor. Confirming a pair shares private history. Rejecting a match separates the current identity and cancels pending Instagram replies." />
      <div className="space-y-4 p-5 text-sm">
        {candidates.length === 0 && <p>No identity matches to review yet.</p>}
        {candidates.map(row => {
          const other = identities.find(i => i.id === row.candidate_id);
          return <div key={row.id} className="flex flex-wrap items-center gap-3">
            <span>{name(row)} → {other ? name(other) : "another saved identity"} · {row.status}</span>
            {row.status !== "verified" && <button disabled={pending} className={button} onClick={() => run("verify", row.id, row.candidate_id!)}>Confirm same person</button>}
            <button disabled={pending} className={button} onClick={() => run("reject", row.id, row.candidate_id!)}>Different person</button>
          </div>;
        })}
        <div className="flex flex-wrap gap-3 border-t border-[var(--app-border)] pt-4">
          <select aria-label="First identity" className="app-input" value={first} onChange={e => setFirst(e.target.value)}>
            <option value="">Choose a contact</option>{identities.map(i => <option key={i.id} value={i.id}>{name(i)}</option>)}
          </select>
          <select aria-label="Identity on another channel" className="app-input" value={second} onChange={e => setSecond(e.target.value)}>
            <option value="">Their other account</option>{identities.filter(i => i.id !== first).map(i => <option key={i.id} value={i.id}>{name(i)}</option>)}
          </select>
          <button className={button} disabled={pending || !first || !second} onClick={() => run("verify", first, second)}>Confirm these accounts</button>
        </div>
      </div>
    </Card>
    <Card>
      <CardHeader title="Instagram delivery" description={`History import: ${syncStatus}. Due times remain subject to her schedule and the current messaging window.`} />
      <div className="space-y-4 overflow-x-auto p-5 text-sm">
        {circuitUntil && <p>Provider pause until {circuitUntil}. No automatic resend of an uncertain result.</p>}
        {queue.length === 0 ? <p>No queued or recent actions.</p> : <table className="w-full text-left text-xs">
          <thead><tr><th className="p-2">Action</th><th className="p-2">Status</th><th className="p-2">Scheduled (UTC)</th><th className="p-2">Detail</th></tr></thead>
          <tbody>{queue.map(a => <tr key={a.id} className="border-t border-[var(--app-border)]">
            <td className="p-2">{a.kind} {a.igsid}</td><td className="p-2">{a.state}</td>
            <td className="whitespace-nowrap p-2">{a.due_at.replace("T", " ").slice(0, 19)}</td><td className="p-2">{a.reason || a.text.slice(0, 100)}</td>
          </tr>)}</tbody>
        </table>}
        {takeovers.map(user => <div key={user.igsid} className="flex items-center gap-3">
          <span>@{user.username || user.igsid} · manual takeover</span>
          <button disabled={pending} className={button} onClick={() => run("resume", user.igsid)}>Resume on next message</button>
        </div>)}
      </div>
    </Card>
    <Card>
      <CardHeader title="Approved Instagram photo" description="Select a normal SFW image from her active album. Each person can receive at most one. Selecting it does not enable photo sending." />
      <div className="space-y-4 p-5">
        <select className="app-input" aria-label="Approved photo" value={photoId} onChange={e => setPhotoId(e.target.value)}>
          <option value="">No photo selected</option>{photos.map(p => <option key={p.id} value={String(p.id)}>{p.caption || `Photo ${p.id}`}{p.instagram_approved ? " · approved" : ""}</option>)}
        </select>
        {chosen && <Image src={chosen.url} alt={chosen.caption || "Selected SFW photo"} width={160} height={200} unoptimized className="rounded-lg object-cover" />}
        <button disabled={pending || !photoId} className={button} onClick={() => run("photo", photoId)}>Approve this SFW photo</button>
      </div>
    </Card>
    <Card>
      <CardHeader title="Test with your own account" description="A two-hour schedule exception for one imported Instagram contact. Off, approval, messaging-window and quota rules still apply." />
      <div className="flex flex-wrap items-center gap-3 p-5">
        <input aria-label="Your test Instagram username" className="app-input" value={testUser} onChange={e => setTestUser(e.target.value)} />
        <button disabled={pending} className={button} onClick={() => run("test", testUser)}>Start two-hour test</button>
        {testUntil && <><span className="text-xs">Until {testUntil}</span><button disabled={pending} className={button} onClick={() => run("end_test", "")}>End test</button></>}
      </div>
    </Card>
  </div>;
}
