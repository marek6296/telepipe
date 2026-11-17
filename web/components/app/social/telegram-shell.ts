"use client";
import { useEffect } from "react";

type Insets = {top:number; bottom:number; left:number; right:number};
export type TelegramWebApp = {
  initData:string; viewportHeight:number; colorScheme:"light"|"dark";
  safeAreaInset?:Insets; contentSafeAreaInset?:Insets;
  themeParams:{bg_color?:string; secondary_bg_color?:string; text_color?:string; hint_color?:string};
  ready:()=>void; expand:()=>void; isVersionAtLeast:(version:string)=>boolean;
  setHeaderColor:(color:string)=>void; setBackgroundColor:(color:string)=>void;
  onEvent:(event:string,handler:()=>void)=>void; offEvent:(event:string,handler:()=>void)=>void;
  BackButton:{show:()=>void;hide:()=>void;onClick:(handler:()=>void)=>void;offClick:(handler:()=>void)=>void};
};
export function telegramWebApp():TelegramWebApp|undefined {
  return (window as Window & {Telegram?:{WebApp:TelegramWebApp}}).Telegram?.WebApp;
}
export function useTelegramShell(ready:boolean,back:(()=>void)|null) {
  useEffect(() => {
    if (!ready) return;
    const app = telegramWebApp();
    const root = document.getElementById("mini-shell");
    if (!root) return;
    function update() {
      if (!root) return;
      const viewport = window.visualViewport;
      const height = Math.min(app?.viewportHeight || window.innerHeight,viewport?.height || window.innerHeight);
      root.style.setProperty("--mini-height",`${height}px`);
      root.style.setProperty("--mini-top",`${viewport?.offsetTop || 0}px`);
      for (const edge of ["top","bottom","left","right"] as const) {
        root.style.setProperty(`--mini-safe-${edge}`,`${Math.max(app?.safeAreaInset?.[edge] || 0,app?.contentSafeAreaInset?.[edge] || 0)}px`);
      }
      root.dataset.theme = app?.colorScheme || "dark";
      const theme = app?.themeParams;
      for (const [property,value] of [["--app-bg",theme?.bg_color],["--app-surface",theme?.secondary_bg_color],["--app-text",theme?.text_color]]) {
        if (property && value) root.style.setProperty(property,value);
        else if (property) root.style.removeProperty(property);
      }
      // SDK methods absent on older Telegram clients must not block login.
      if (app?.isVersionAtLeast("6.1")) { app.setHeaderColor(app.isVersionAtLeast("6.9") ? theme?.bg_color || "#0a0a0a" : "bg_color"); app.setBackgroundColor(theme?.bg_color || "#0a0a0a"); }
    }
    app?.ready(); app?.expand(); update();
    const events = ["themeChanged","viewportChanged","safeAreaChanged","contentSafeAreaChanged"];
    for (const event of events) app?.onEvent(event,update);
    window.visualViewport?.addEventListener("resize",update);
    window.visualViewport?.addEventListener("scroll",update);
    window.addEventListener("resize",update);
    return () => {
      for (const event of events) app?.offEvent(event,update);
      window.visualViewport?.removeEventListener("resize",update);
      window.visualViewport?.removeEventListener("scroll",update);
      window.removeEventListener("resize",update);
    };
  },[ready]);
  useEffect(() => {
    if (!ready) return;
    const app = telegramWebApp();
    if (!app?.isVersionAtLeast("6.1")) return;
    if (!back) { app.BackButton.hide(); return; }
    app.BackButton.show(); app.BackButton.onClick(back);
    return () => { app.BackButton.offClick(back); app.BackButton.hide(); };
  },[ready,back]);
}
