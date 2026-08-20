"use client";

import { usePathname } from "next/navigation";

/**
 * Prechod medzi obrazovkami.
 *
 * PREČO CSS A NIE FRAMER-MOTION
 * -----------------------------
 * Nie preto, že by framer nefungoval — to som netestoval poctivo. Dôvod je
 * jednoduchší: toto je jediná animácia, ktorá beží pri KAŽDEJ navigácii, a keby
 * zlyhala, ostane namiesto obrazovky prázdne miesto. CSS animáciu pustí
 * prehliadač sám pri vložení prvku do DOM; nezávisí od hydratácie, od toho, či
 * sa JS stihol načítať, ani od toho, čo práve robí hlavné vlákno. Pri veci
 * s takouto cenou zlyhania je to rozumnejšia stávka — a je zadarmo.
 *
 * ANIMÁCIA NIČ NEZDRŽUJE
 * ----------------------
 * Žiadne čakanie na odchod starej obrazovky (`mode="wait"` by pridalo presne
 * ten čas, ktorý sme odstránili presunom funkcií do Dublinu). Nová sa len
 * vloží a nabehne — človek vidí pohyb od prvého snímku, takže tých ~130 ms
 * čakania na dáta nevníma ako prázdno.
 *
 * KĽÚČ JE `pathname`
 * ------------------
 * Zmena kľúča vloží nový prvok, čím sa animácia spustí odznova. Kostra
 * z `loading.tsx` aj hotový obsah zdieľajú tú istú cestu, takže výmena kostry
 * za obsah už neanimuje — inak by to bliklo dvakrát po sebe.
 *
 * Query parametre sa zámerne ignorujú: prepnutie platformy na Virtual SIM
 * (`?service=whatsapp`) je zmena obsahu jednej obrazovky, nie prechod inam.
 *
 * AK TO IDEŠ TESTOVAŤ: v skrytej karte prehliadača sú animácie zmrazené a
 * `getComputedStyle` ukáže `opacity: 0` aj pri úplne zdravej animácii. Nedá sa
 * z toho usudzovať nič — over to cez `element.getAnimations()` (`playState`
 * a stav po `finish()`), alebo s kartou naozaj v popredí.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="app-page-in">
      {children}
    </div>
  );
}
