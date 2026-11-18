import type {SocialChannel,SocialSite} from './social-types';

function safeUrl(value:unknown):string|null {
  if(typeof value!=='string' || !value.trim() || /\s/.test(value.trim()))return null;
  try{const url=new URL(value.trim());return url.protocol==='https:' && !url.username && !url.password ? value.trim():null;}catch{return null;}
}

/** Public destinations only; account credentials never enter this DTO. */
export function configuredSites(persona:Record<string,unknown>|null,instagram:Record<string,unknown>|null,channel:SocialChannel):SocialSite[]{
  const sites:SocialSite[]=[];
  const cta=safeUrl(persona?.cta_link);
  if(cta){const fanvue=/^https:\/\/(?:www\.)?fanvue\.com\/[^\s@]+$/.test(cta);
    sites.push({kind:fanvue?'fanvue':'website',label:fanvue?'Fanvue':'Website',url:cta,available:fanvue||channel!=='instagram',reason:channel==='instagram'&&!fanvue?'Use a configured platform link on Instagram.':''});}
  const page=safeUrl(instagram?.bio_link);
  if(page && ['linkovne.com','www.linkovne.com'].includes(new URL(page).hostname) && new URL(page).pathname.replaceAll('/','') && (!new URL(page).port || new URL(page).port==='443')){
    sites.push({kind:'linkovne',label:'Linkovne',url:page,available:true,reason:''});
  }
  const handle=typeof instagram?.telegram_handle==='string'?instagram.telegram_handle.trim().replace(/^@/,''):'';
  if(/^[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(handle)){
    sites.push({kind:'telegram',label:'Telegram',url:`https://t.me/${handle}`,available:true,reason:''});
  }
  return sites.filter((s,i)=>sites.findIndex(other=>other.url===s.url)===i);
}
