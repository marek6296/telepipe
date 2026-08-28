# Ako otestovať lacnejší režim (Economy)

Scenár na **Test chat** v control botovi (`🧪 Test chat`). Vety nie sú
vymyslené — sú to skutočné správy z Simoniných telegramových chatov, vybraté
tak, aby trafili presne tie miesta, kde sa lacnejší model najskôr zlomí.

## Prečo Test chat a nie skutočný účet

Test chat používa **ten istý** `build_system_prompt` a to isté čistenie
odpovede ako ostrá prevádzka, ale históriu drží len v pamäti procesu — do
štatistík, pamäte ani denného súhrnu sa nedostane nič. Reštart ju zmaže.

Neposiela sa pri ňom „videné", nespotrebúva sa žiadny skutočný lead a nehrozí
Telegram flood z automatickej komunikácie medzi dvoma vlastnými účtami.

`🔄 Fresh start` v bote zmaže skúšobnú konverzáciu a začne odznova — medzi
kolami ho použi, inak si modelka pamätá predchádzajúci pokus.

## Postup

1. V appke over, že Mio má **Conversation quality → Economy**.
2. V botovi prepni na Mio a otvor `🧪 Test chat`.
3. Posielaj vety nižšie **po jednej** a čítaj odpoveď.
4. Potom `🔄 Fresh start`, prepni Mio na **Quality** a celé zopakuj.
5. Porovnaj obe kolá vedľa seba.

## Scenár (12 správ)

| # | čo posielaš | čo sleduješ v odpovedi |
|---|---|---|
| 1 | `hey` | Predstaví sa ako človek? Nezačne dotazníkom? |
| 2 | `Hmm how do you make money off that? I am unfamiliar with online. I work as an installer in air conditioning. I go to the gym too. I am fit 😉` | Odpovie na OBE veci — svoju prácu aj jeho? Alebo len na jednu? |
| 3 | `It's very expensive out there. You must make good money` | Drží krycí príbeh, alebo si vymyslí nový? |
| 4 | `I did not realize you even got back to me. But hiking is fun laziness is not hahahah` | Rozumie vtipu? Lacný model tu často odpovie doslovne. |
| 5 | `I mean i don't like writing with a bot. 😕` | **Najdôležitejšia.** Ustojí to bez obhajovania sa a bez „I am not a bot"? |
| 6 | `oh okey, can we call sometime?` | Odmietne mäkko a nechá dvere otvorené? |
| 7 | `So i can't ever meet you for real?` | Neurazí sa, neuteká, nesľúbi stretnutie? |
| 8 | `I am a barber. What videos do you have?` | Zapamätala si si, že je inštalatér klimatizácií (#2)? **Tu sa pamäť láme najčastejšie.** |
| 9 | `where do all the photos go?` | Ukáže na stránku ROVNO, alebo to odloží na neskôr? |
| 10 | `Your Instagram is on another level! Definitely a body I would love too inspect from top to bottom 💋🥵` | Zvládne priostriť a naviazať na jeho slová? |
| 11 | `I don't like paying for content because it just does not feel exclusive to me` | Podrží rámec ako Colin („feels better when u earn it"), alebo zľavuje a prosíka? |
| 12 | `Yes, actions speak louder than words. I hope we meet each other one day. I like our chemistry` | Uzavrie to teplo, ale bez sľubu, ktorý nesplní? |

## Na čo sa pri porovnaní pozerať

Nie na to, či je odpoveď „pekná" — na to, či **robí to, čo má**:

- **Pamäť** (#8) — zamieňa si fakty o ňom?
- **Konzistencia príbehu** (#3) — protirečí si o práci a peniazoch?
- **Test na bota** (#5) — obhajuje sa, alebo to zhodí?
- **Rámec** (#11) — zľavuje pod tlakom?
- **Dĺžka a rytmus** — píše zrazu odseky namiesto krátkych bublín?
- **Jazyk** — neskĺzne do slovenčiny alebo do formálnej angličtiny?

Keď lacný model prejde #5, #8 a #11, je použiteľný. Keď padne na ktoromkoľvek
z nich, klientovi ho neponúkaj — stratený lead je drahší než ušetrené tokeny.

## Poznámka k cene

Úspora je ~11×, lebo naša cena je zo 100 % vstupné tokeny (za 10 dní 9,25 M
vstup proti 20 tis. výstup) — platí sa za prompt, nie za odpovede. Lacnejší
model teda škáluje celú cenu, nie jej zlomok.
