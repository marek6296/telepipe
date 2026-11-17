type Identity = {channel:string;externalId:string;accountScope:string;identityId?:string|null;identityUpdatedAt?:string|null};
export function briefKey(contacts:Identity[]):string {
  return JSON.stringify(contacts.map(c=>[c.channel,c.externalId,c.accountScope,c.identityId||'',c.identityUpdatedAt||'']).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));
}
export type BriefSource = {account:string;memory:string;rows:{id:string;role:string;content:string;at:string}[];total:number};
export function briefContext(sources:BriefSource[]) {
  let truncated=false;
  const coverage:string[]=[];
  const budget=Math.floor(138000/Math.max(1,sources.length));
  const text=sources.map(source=>{
    const rows=[...new Map(source.rows.map(r=>[r.id,r])).values()].sort((a,b)=>(a.at||'').localeCompare(b.at||'')||Number(BigInt(a.id)-BigInt(b.id)));
    let lines=rows.map(r=>`[${r.at||'date unknown'}] ${r.role==='user'?'PERSON':'MODEL'}: ${r.content.slice(0,2400)}`);
    const original=lines.join('\n');
    const memory=source.memory.slice(0,Math.min(6000,Math.floor(budget/8)));
    const messageBudget=budget-memory.length;
    if(memory.length<source.memory.length)truncated=true;
    if(original.length>messageBudget) {
      lines=[original.slice(0,Math.floor(messageBudget/6)),'[middle omitted]',original.slice(-Math.floor(messageBudget*5/6))]; truncated=true;
    }
    if(source.total>rows.length || rows.some(r=>r.content.length>2400)) truncated=true;
    coverage.push(`${source.account}: ${rows.length} sampled / ${source.total} imported messages`);
    return `ACCOUNT ${source.account}\nSTORED MEMORY (may be outdated):\n${memory}\nMESSAGES:\n${lines.join('\n')}`;
  }).join('\n\n');
  return {text,coverage:coverage.join('\n'),truncated};
}
export function parseBrief(value:unknown):string {
  const summary=value && typeof value==='object' ? (value as Record<string,unknown>).summary : null;
  if(typeof summary!=='string'||!summary.trim()||summary.length>14000) throw new Error('The AI helper returned an invalid summary. Try again.');
  return summary.trim();
}
