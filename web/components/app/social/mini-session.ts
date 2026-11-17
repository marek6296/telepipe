export type MiniModel = {id:string; name:string};
export type MiniSession = {models:MiniModel[];selectedModelId:string;token?:string};

/** A new signed launch must never inherit an unrelated browser cookie session. */
export async function connectMiniSession({bot,initData,fetcher = fetch}: {bot:string|null; initData?:string; fetcher?:typeof fetch}):Promise<MiniSession> {
  if (!bot) throw new Error("Open Social sites using the menu in your paired Telegram bot.");
  const options:RequestInit = {credentials:"include",cache:"no-store",redirect:"error"};
  const response = initData
    ? await fetcher("/api/mini/bootstrap",{...options,method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bot,initData})})
    : await fetcher(`/api/mini/models?${new URLSearchParams({bot})}`,options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Close this window and reopen Social sites from your Telegram bot.");
  return body;
}
