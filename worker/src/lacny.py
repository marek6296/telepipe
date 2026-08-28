"""Barličky pre lacnejší model — to, čo si drahší domyslí sám.

PREČO TO EXISTUJE. Ten istý scenár (12 správ zo Simoniných chatov) prebehol na
oboch modeloch s tým istým promptom. Lacnejší prepadol na štyroch konkrétnych
veciach, a všetky štyri sa dajú povedať nahlas:

  1. OTÁZKA NA KONCI — položil ju v 2 z 12 odpovedí (drahší v 10 z 12).
     Rozhovor mu na jej strane vyhasol.
  2. SKRÁTENÉ TVARY — dôsledne písal „I do not", „It is", „I am". Drahší
     píše „Id", „thats", „Ill". V chate je to najrýchlejší prezradzovač.
  3. FAKTY O ŇOM — v druhej správe povedal, že montuje klimatizácie, v ôsmej
     že je holič. Nevšimol si to; drahší na to nadviazal ešte o tri správy
     neskôr („what do you cut most, fades or longer hair?").
  4. ROZBITÁ PERSONA — na pochvalu jej Instagramu odpovedal „I do not actually
     have an Instagram though". Poprel niečo svoje po tom, čo to fanúšik
     pochválil.

PREČO TO NIE JE V HLAVNOM PROMPTE. Drahší model to všetko robí sám a tieto
vety by mu len ubrali priestor — pri 3 300 tokenoch promptu je každá sekcia
navyše niečo, čo musí prečítať pri každej správe. Toto je barlička, nie
pravidlo produktu.

CENA. Blok má ~220 tokenov, teda ~7 % nášho promptu. Lacnejší model je ale
10,7× lacnejší, takže s barličkou vychádza stále ~10× lacnejšie než drahý.
"""
from __future__ import annotations

# Hlavička musí byť INÁ než „AKO PÍŠEŠ" v `CORE_RULES` — dve rovnako nazvané
# sekcie si model spája a pri rozpore nevie, ktorá platí. Toto je záverečná
# kontrola pred odoslaním, a tak sa aj volá.
BLOK = """NEŽ ODOŠLEŠ — SKONTROLUJ TOTO
- SKONČI TAK, ABY MAL NA ČO ODPOVEDAŤ. Otázka, alebo veta, ktorá si pýta
  reakciu. Nie v každej správe rovnaká — raz sa spýtaj na neho, raz hoď
  niečo o sebe, na čo sa spýta on. Bez toho rozhovor umrie na tebe.
- PÍŠ SKRÁTENE, ako do mobilu: „im", „dont", „thats", „youre", „ill",
  „cant", „gonna". NIKDY „I do not", „It is", „I am", „That is" — tak píše
  úrad, nie dievča na gauči.
- PREČÍTAJ SI, ČO O SEBE POVEDAL, a nadviaž na to. Čo robí, kde býva, čo mal
  cez deň. Keď povie niečo nové o sebe, VŠIMNI SI TO nahlas — aj keď to
  nesedí s tým, čo hovoril predtým.
- NIKDY NEPOPIERAJ NIČ SVOJE. Keď spomenie tvoj Instagram, tvoje video alebo
  čokoľvek tvoje, choď s tým — aj keby si o tom nevedela. „To nemám" je to
  najhoršie, čo môžeš napísať; znie to, akoby si nebola ty.
- NEVYMENÚVAJ, ČO MÁŠ ZA OBSAH. Žiadne zoznamy. Spomeň JEDNU vec tak, aby sa
  pýtal ďalej.
- JEDNA MYŠLIENKA NA SPRÁVU, dve vety stačia. Radšej kratšie a živšie než
  dlhé a vysvetľujúce."""


def blok(chat_tier: str) -> str:
    """Sekcia do promptu. Prázdna pri kvalitnom režime.

    Neznámy režim nedostane nič — rovnako ako `Llm.set_chat_tier` ide pri
    preklepe na kvalitný model, tu sa pri ňom nepridáva barlička.
    """
    return BLOK if str(chat_tier or "") == "economy" else ""
