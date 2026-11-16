# Instagram a spoločná pamäť konverzácií

Stav: **spoločná vrstva a Instagram fronta implementované a nasadené 2026-11-16** podľa realizačného plánu a Marekovho pokynu prevziať všetky rozhodnutia. Na Marekov výslovný pokyn je Instagram od 15:42 UTC v Semi, import je zapnutý; živý outbound test zostáva na majiteľovi. Číselné limity sú produktové stropy, nie záruka účtu bez blokácie. Sekcie 1–18 zachovávajú pôvodný návrh; presný rozsah a overenie dodávky sú nižšie.

## Nasadený výsledok a overenie

- Worker `9984dfc9d4c0d316f7cc773b004da48b691cc333`, Railway deployment `a970af0e-e867-4ff9-8d37-40c0877f397b` SUCCESS. Vercel web `dpl_22VqskaQLxq1tVsxAMhbGkRbMCSG` READY na rovnakom SHA.
- Supabase aplikované migrácie `shared_conversations`, `conversation_rollout_controls`, `identity_change_pending_replies`, `instagram_destination_budgets`. Nové tabuľky majú owner-read RLS, mutačné RPC iba service_role; overené aj na produkčných grantoch.
- TG/IG/FV používajú uložený spoločný deň, stabilný mierny tón, auditované identity a kontext overenej osoby. Automatické rozpoznanie zostáva vratnou indíciou. Potvrdenie súkromnej pamäte dnes robí majiteľ v Telepipe; automatický bezpečnostný challenge medzi účtami nie je súčasťou dodávky.
- Pamäť používa existujúce kanálové archívy a posledných 12 správ z každého ďalšieho overeného účtu (max 16 000 znakov spolu). Pôvodná vlastná pamäť každého kanála zostáva. Rozsiahly nový graf faktov/epizód z návrhu nebol zavedený a nejde o garanciu úplnej znalosti všetkých historických detailov.
- IG: durable ingest/fronta, pôvodné časy, LA dostupnosť, reprodukovateľné odstupy, databázové rezervácie a limity, versioned Semi, kontrola aktuálneho remote kontextu, ručný takeover, uncertain bez slepého retry. Komentáre iba v Auto; DM a reakcie rešpektujú zvolený režim. API verejné lajky a týždenné organické follow-upy sa nezapínajú.
- URL iba presný Telegram alebo Linkovne profil, Telegram max 4/LA deň aj rolling 24 h a odstup 2 h; Linkovne max 2 a odstup 4 h; spolu max 6 a odstup 1 h. Jeden propagačný URL na osobu naprieč oboma cieľmi. Highlights/reminder formuluje persona kontextovo, nie zo šablóny. Jedna schválená aktívna SFW fotka; žiadny IG hlas. Pozvania/fotka vyžadujú dospelý vek deklarovaný používateľom alebo doložený platformou; neznámy/sporný vek ich nepovolí.
- Opt-out sa prenáša na overené účty. Nová konkrétna otázka po odmietnutí kontaktu môže dostať obyčajnú reaktívnu odpoveď; neobnovuje odkazy ani proaktívny kontakt. Výslovný súhlas obnoví odpovede, nie marketing. Zmena/odmietnutie identity zneplatní čakajúce návrhy na všetkých kanáloch.
- Simona: `connected=true`, `reply_mode=semi`, `enabled=true`, `funnel_target=both`, import/reactions/comments/highlights/typo nakonfigurované; Telegram `simapussina`. Linkovne `https://linkovne.com/simonakralova` uložená. Nové Semi návrhy obsahujú presnú URL pred schválením; zmena rozpočtu ju nesmie potichu vymeniť. Neznáme/kombinované ručné URL sa započítajú do oboch rozpočtov; pripomenutie zachová pôvodný cieľ pozvania. Fotky vypnuté, kým vyberie konkrétny obrázok. Existujúce TG/FV režimy sa nemenili.
- Živý read-only dôkaz: profil, Conversations a posts/comments API úspešné; import ukladá skutočné konverzácie a manuálne odoslania. Prvá Meta chyba 1 bola dočasná: rovnaká požiadavka následne úspešná, bezpečnostná pauza ručne zrušená až po overení, bez úpravy API kontraktu.
- Majiteľ explicitne identifikoval `dony.donoval` ako seba; spojený s modelkiným párovaným `owner_chat_id`. Reálne volania ConversationHub overili súkromný kontext IG → TG aj TG → IG bez generovania/odosielania správy.
- **Testy:** 2 423 worker testov prešlo, 2 integračné deselected; pôvodne chýbajúci ffmpeg vyriešený izolovaným lokálnym binárnym súborom, bez zmeny závislostí aplikácie. Všetky štyri skutočné migrácie prešli disposable PGlite kontraktmi, vrátane opravy identity/kvót/lease/RLS. PGlite je jedna connection, nie test súbehu dvoch reálnych serverových spojení. Web typecheck, zmenené ESLint súbory, Instagram skripty a production build prešli. Pôvodné UI overené v prihlásenom prehliadači; následné zapnutie Semi a oba ciele overené cez produkčnú DB.
- **Hranica overenia:** žiadne živé DM/reakcie/fotky/komentáre fanúšikom sa neposielali; outbound Meta flow a výsledná kvalita textu ešte vyžadujú majiteľov Semi test. Štandardný prístup/aplikácia v development režime nie je Advanced Access pre cudzích klientov. Úplný starý archív ani 100 % správne rozhodnutie v každej situácii sa nesľubuje.

- Po aktuálnom nasadení: živý read-only Meta read 5 chatov za 9.9 s; worker poll 15:42:48 UTC, `poll_error` prázdne a žiadna provider pauza. Meta 0 pred nasadením bol čítací výpadok; konkrétna príčina nebola dokázaná. Stránka znížená z 25 na 5 kvôli nákladným vnoreným správam. Staré správy sa po zapnutí Semi automaticky nevybavujú.

### Záver nezávislého review

Čerstvý whole-branch review: 0 Critical, 6 Important, 1 Minor. Všetko opravené s regresiami: (1) CHECK manuálneho importu a obnoviteľné vedľajšie účinky, (2) správne miesto overenia platobnej identity, (3) spoločný stop na send hraniciach TG/FV aj staré schválenia, (4) rovný/typografický apostrof v odmietnutí, (5) znovu overený foto zámer/vek pri retry, (6) návrat po opt-out bez obnovenia marketingu. Minor o preklepe po schválení prehodnotený na Important: schválený text sa nemení. Žiadne odložené drobnosti. Následná kontrola nasadenia pridala SQL regresiu a trigger zneplatnenia návrhov všetkých kanálov po zmene identity (RED → GREEN).

Následný review samostatných rozpočtov našiel 1 Important (zmiešané ručné URL) a 1 Minor (pripomenutie mení cieľ pozvania). Obe opravené; regresie overujú skutočné `instagram_record_manual` a `process_one`, vrátane schemeless URL.

Rozhodnutia pri realizácii: delegované schválenie pokrýva merge/push/deploy bez ďalšieho menu; žiadny paralelný lokálny Telethon worker; automatické rozpoznanie neznamená prístup k cudzej súkromnej histórii; nepodporované Meta schopnosti sa nesimulujú. Podrobný [realizačný plán](../plans/2026-11-16-shared-conversations.md).

## 1. Výsledok, ktorý chceme

Jedna modelka má jednu personu, jeden deň, konzistentný štýl a pamäť konkrétneho človeka. Instagram, Telegram a Fanvue sú rôzne miesta, kde sa s ním stretáva. Prechod medzi miestami nemá resetovať vzťah ani miešať údaje dvoch ľudí.

Instagram má odpovedať primerane obsahu a dostupnosti, s odstupmi a stropmi; neodpovedá na všetko. Podporí DM, textové odpovede na stories, reakcie na vhodné DM, vybrané verejné komentáre a najviac jednu schválenú bežnú fotku pre kontakt. Hlasovky na IG zostanú vypnuté. Spresnenie Mareka: **na IG iba Telegram alebo osobná stránka Linkovne; priamy Fanvue odkaz nie**. Po vyčerpaní interného denného limitu URL môže pri vhodnej príležitosti upozorniť na existujúci odkaz v Highlights bez URL; aj také pozvanie má vlastný odstup a nesmie obísť časové okno ani pauzu účtu.

Prirodzenosť znamená kontext, stručnosť, primeraný humor a konzistentné hranice. Marek dodatočne zdôraznil: **každú formuláciu vrátane Highlights musí napísať Simona svojím existujúcim štýlom, bez diakritiky a v nadväznosti na celú konverzáciu**. Príklady v návrhu nie sú šablóny na odoslanie. Nie je to maskovanie automatizácie pred platformou ani sľub, že systém rozpozná každú situáciu. Pri neistote má bezpečný výsledok: počkať, overiť jednu vec, alebo odovzdať chat Marekovi.

## 2. Prístupy a zvolený návrh

| Prístup | Dôsledok |
|---|---|
| Doplniť IG prompt o pauzy, nálady a pravidlá | Rýchle, ale prompt nezaručí limit, uloženie stavu, správnu identitu ani rovnaký deň. Nevhodné ako základ. |
| Spoločná vrstva identity, pamäte, dňa a odosielania; samostatné pravidlá kanálov | Odporúčanie autora. Zachová existujúci dobrý TG štýl, umožní postupný prechod a jedno miesto na pevné pravidlá. |
| Prepísať všetkých troch agentov naraz | Veľká regresná plocha a zbytočný zásah do fungujúceho Telegramu. Odložiť. |

Marek delegoval návrhové voľby; druhý prístup je odporúčanie Codexu, nie dodatočne vymyslené schválenie implementácie. Jednotlivé kanály budú prechádzať na spoločné služby postupne.

## 3. Čo existuje a čo chýba

| Oblasť | Zistenie z kódu | Potrebná zmena |
|---|---|---|
| Persona | IG používa `persona.build_system_prompt` a čistenie z TG | Zachovať štýl; oddeliť spoločné jadro od obchodných pravidiel konkrétneho kanála. |
| Denný režim | IG nemá časovú bránu ani `den.block_at`; TG používa model ID, FV meno ako seed | Jeden uložený plán dňa s rovnakou revíziou pre všetky kanály. |
| Pamäť | IG má vlastné `ig_users/ig_messages`; nie je napojený na identitu TG/FV | Spoločný kontakt, overené identity, zdieľané fakty s pôvodom a kontext kanála. |
| TG → FV | `fanmatch.py` spája aj podľa podobnosti mena a čerstvého kliku; FV číta TG kontext | Heuristika bude iba kandidát. Klik je atribúcia, nie dôkaz vlastníctva oboch účtov. Doplniť opačný smer a IG. |
| Import | IG načíta 25 konverzácií a 20 správ na konverzáciu, bez stránkovania zoznamu | Import dostupnej histórie, kurzory, pôvodné časy, záznam o neúplnosti. |
| Časy správ | `add_message` nepersistuje čas z platformy; `last_incoming_at` sa nastavuje na čas pollu | Oddeliť `occurred_at` a `ingested_at`; okno počítať výhradne zo skutočnej oprávnenej udalosti. |
| Odoslanie | `not nove` rozhoduje, či odpovedať; po chybe sa už importovaná správa nemusí znovu vybaviť | Trvalá fronta práce oddelená od deduplikácie príjmu. |
| Semi | `deliver_text` má komentár o okne, ale v tele znovu nekontroluje okno, Off ani takeover | Jedna spoločná brána tesne pred každým odoslaním vrátane schváleného textu. |
| Komentáre | Až tri odpovede bez odstupu v kole; výber hlavne cez LLM `SKIP` | Výber pred generovaním, uložené rozhodnutie, samostatné splatné časy. |
| Stories | Médium bez textu sa zlieva do jedného placeholdera | Typ udalosti, `reply_to`, story ID a dostupný kontext. |
| Fotky/reakcie | IG API klient má text a komentárové odpovede; fotky/hlas sú stub | DM reakcie a jedna bezpečná fotka ako osobitné capability a akcie. |
| Odkazy | IG pravidlá aj sanitizer zakazujú všetky URL | Povoliť len uložené ciele a atómový rozpočet, upraviť všetky vrstvy naraz. |

Toto sú výsledky čítania kódu, nie reprodukcia každej chyby v produkcii. Pri audite je účet pripojený a odpisovanie Off. Produkčné nastavenia sa týmto dokumentom nemenia.

## 4. Overené hranice platformy

1. Bežný IG rozhovor má automatické okno 24 hodín od oprávnenej vstupnej správy. Automatické pripomenutie po týždni preto pre organické DM nenavrhneme. Pri rozhovoroch z Click-to-Direct reklamy Meta uvádza osobitné okno do siedmich dní od prvej správy po reklame; nezapínať ho bez preukázaného pôvodu. `HUMAN_AGENT` je pre ľudské odpovede, nie obchádzka pre naplánovanú AI. [Send Messages](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api), [Messaging policy](https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy)
2. API podporuje reakciu na konkrétnu správu. To je odlišné od lajku stories alebo verejného komentára. [Send Messages – reactions](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api#react-or-unreact-to-a-message)
3. Nový endpoint `POST /<IG_USER_ID>/likes` podporuje médiá a komentáre, ale dokumentácia ho uvádza **iba pre Facebook Login**, s `instagram_manage_engagement` a prístupom k prepojenej Page. Stories nepodporuje. Na dnešnom Unified Login preto `comment_like=false`, kým sa nepotvrdí podporovaný prístup. Žiadne prihlasovanie súkromným heslom ani simulovanie klikania ako náhrada. [User Likes](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/user-likes)
4. Pri histórii dokumentácia uvádza detail posledných 20 správ konverzácie. Úplný starý archív nie je možné sľúbiť len pripojením API. [Conversation reference](https://developers.facebook.com/docs/graph-api/reference/conversation/)
5. Webhooky majú vlastné požiadavky na Live app a produkčný prístup; komentárové webhooky vyžadujú Advanced Access. Aktuálny vývojový režim nesmie byť návrhom vydávaný za pripravenú webhook produkciu. [Webhook setup](https://developers.facebook.com/documentation/instagram-platform/webhooks/setup)
6. Meta odporúča oznámiť automatizáciu a osobitne upozorňuje na California market. Prístup k automatizácii bude zrozumiteľný; pri priamej otázke sa nebude nepravdivo tvrdiť, že píše živý človek. Existujúci `REAL_MODE` potrebuje v tejto vetve nahradiť pravdivou identitou virtuálnej postavy. Nejde o zmenu jej slovníka ani charakteru. [Messaging policy](https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy)

Linkovne je bežná stránka s odkazmi, nie výnimka z pravidiel obsahu či spamu. Rovnako prepísanie URL na handle nerobí zo správy automaticky povolenú správu. API priepustnosť a kvalita interakcií sú dve rôzne veci; neexistuje tu overený počet „bezpečných správ proti banu“.

## 5. Jedna osoba, jeden deň

Spoločné `model_day_state` sa vytvorí raz pre modelku a lokálny deň z `model_id`, dátumu a verzie rozvrhu. Obsahuje aktivity, vstávanie, dostupnosť, energiu a tón. Všetci agenti čítajú totožný uložený výsledok. Existujúce texty persony, jazyky, lokality a zvyklosti zostanú východiskom; nevymýšľa sa nová Simona.

- Časová zóna `America/Los_Angeles`, nie pevné UTC−8. Ukladanie UTC, rozhodovanie cez IANA zónu; testovať letný čas a opakovanú hodinu.
- Dnešné nastavené aktívne okno sa zachová. Dostupnosť je prienik aktívneho okna a reálneho bloku dňa; pred vylosovaným vstávaním neodpovedá len preto, že už začalo široké aktívne okno.
- Po polnoci do zaspania pokračuje večer predchádzajúceho dňa. Denný účtovný limit sa napriek tomu počíta podľa kalendárneho dňa LA a zároveň má kĺzavý 24-hodinový strop.
- Zmena rozvrhu sa štandardne použije nasledujúci deň. Ručná zmena dneška má revíziu a zruší neaktuálne návrhy; nemá spätne prepísať už uložené udalosti.
- Nálada = mierna zmena energie, hravosti a dĺžky odpovedí. Základ drží celý deň, zmena najskôr po 4–8 hodinách alebo odôvodnenej udalosti. Nie nový náhodný stav pri každej správe.
- Správanie voči kontaktu je oddelené: priateľský, opatrný, stručné hranice, pauza. Jeden dotieravý človek nezmení tón k všetkým ostatným.
- Fanvue môže mať pozornejší zákaznícky tón, no platba nemení fakty o dni, nevymaže blokáciu ani súhlas. Potvrdený nákup vedie ku krátkemu primeranému poďakovaniu, nie k vymyslenej intimite či tlaku na ďalšiu platbu.
- Plán postavy nie je dôkaz skutočnej udalosti. Nesmie tvrdiť „práve som ti to odfotila“, keď odosiela starší schválený obrázok.

## 6. Identita človeka naprieč kanálmi

Každý kontakt má interné `person_id` **v rámci konkrétnej modelky**. Identita je `(model_id, platform, account_scope, external_user_id)`. Username je meniteľný alias s históriou, nie primárny kľúč. Kontakty iných modeliek sa bez ďalšieho súhlasu nespájajú.

Stavy prepojenia: `unlinked → candidate → awaiting_confirmation → verified`; ďalej `rejected`, `revoked`. Len `verified` sprístupňuje súkromnú pamäť iného kanála. Kandidát má dôvody, protidôkazy a dátum; model nesmie skóre zmeniť na istotu.

| Dôkaz | Použitie |
|---|---|
| Rovnaký/podobný username, meno, jazyk, čas príchodu | Návrh kandidáta; nikdy automatické zlúčenie. Žiadne porovnávanie tváre. |
| Klik na osobný odkaz, následný nákup | Atribučná indícia. Odkaz možno preposlať a časová blízkosť neoveruje totožnosť. |
| „Som ten z Instagramu“ | Jedna prirodzená otázka na jeho IG meno, nie odhalenie uložených súkromných detailov. Potom potvrdenie účtov. |
| Jednorazový kód poslaný v jednom prihlásenom chate a vrátený v druhom | Dôkaz kontroly oboch koncových účtov v rámci našej konverzácie; krátka platnosť, limit pokusov, jedna spotreba. |
| Majiteľ ručne potvrdí oba konkrétne účty | Overené s auditným záznamom, možnosťou odpojiť a znovu zostaviť pamäť. |
| Odmietnutie „nie, to nie som ja“ | Zamietnuť kandidáta, nepýtať sa znova pri každej správe, konverzácia pokračuje ako samostatná. |

Bez dôkazu možno povedať „Did we talk on Instagram before?“ Pri náznaku od človeka „What’s your @ there?“; pred potvrdením nevytiahnuť jeho údajné mesto, predchádzajúcu osobnú tému ani nákup. Po potvrdení môže prirodzene nadviazať na poslednú relevantnú tému, bez druhého zoznamovania.

Telegram modelky je **userbot**, nie bot s `/start` payloadom. Nepredpokladať, že `t.me/<username>?start=...` prenesie identitu. Kód môže byť krátky text, ktorý človek pošle do druhého chatu. Požiadavka na kód je transakčná, nevyvoláva automatický propagačný link.

Kód: náhodný, uložený ako hash, viazaný na modelku, konkrétny zdrojový účet a cieľový kanál, TTL 15 min, max 5 pokusov, atomická spotreba. Ak nie je možné overiť oba konce v povolenom okne, ručné potvrdenie alebo samostatný kontakt. Nepripájať na základe poznania cudzieho username.

Staré `fv_users.tg_id` s neznámym pôvodom označiť `legacy_unverified`, nie hromadne povýšiť na dôkaz. Nová pamäť ich nepoužije ako potvrdenú identitu. Historické reporty a atribúcia zostanú čitateľné s týmto označením. Nové platby patria najprv konkrétnemu FV ID; prenos „paid“ na TG/IG až po overení identity.

Prepnutie musí byť spoločné pre všetkých konzumentov: najprv nasadiť guard do FV čítania `telegram_context`, `_try_link`, `_oznac_zaplateneho`, TG funnel/taper a IG. Až potom pre danú modelku zapnúť `identity_policy_version=2`; stará priama cesta cez `fv_users.tg_id` už nesmie obísť guard. Snapshot väzieb zachová atribúciu, ale neslúži ako dôkaz identity. Zhrnutia odvodené z neovereného iného kanála sa z aktívneho kontextu vyradia a prepočítajú z lokálnych zdrojových správ. Starý TG `paid=true` bez dôkazu dostane stav `legacy_payment_unknown`: nepredstiera potvrdenú platbu, ale ani automaticky neobnoví predajný tlak na možného zákazníka. FV nákupy a nároky samotného FV účtu zostanú platné. Prechod zruší čakajúce akcie závislé od starej identity; na modelke smie byť iba jedna aktívna verzia politiky.

## 7. Pamäť a kontext odpovede

Uchovávame dostupné správy vrátane ručne odoslaných, ich skutočné časy, kanál, smer, pôvod `owner/automation/import/unknown`, platformové ID a väzby na médiá. Pri médiu bez dostupného obsahu sa nepredstiera, že ho videla.

Pamäť má oddelené vrstvy:

1. Fakty: meno, preferovaný jazyk, témy a explicitne povedané preferencie. Každý fakt má zdrojovú správu, čas, istotu a revíziu; vlastný text AI nie je dôkaz o človeku.
2. Kontext vzťahu: posledná téma, nezodpovedané otázky, sľuby, hranice, preferovaný kanál a overená identita. Intímne údaje sa automaticky nekopírujú do verejných odpovedí.
3. História akcií: odkazy, fotka, reakcie, ručné zásahy, opt-out, úspech/neistota doručenia.
4. Komerčné udalosti: návšteva, registrácia, predplatné, konkrétny potvrdený nákup a refund sú odlišné fakty. „Zaplatil som“ v správe nie je platba.

Prompt na odpoveď: spoločná persona → aktuálny kanál a povolené akcie → spoločný deň → overený kontakt → posledných približne 20 správ aktuálneho kanála → krátke relevantné zhrnutie ostatných overených kanálov → dnešná vstupná správa → obmedzenia konkrétnej odpovede. Cudzie správy sú dáta, nie pokyny meniace limity alebo identitu.

Zhrnutie sa aktualizuje po 8–12 nových ťahoch alebo konci rozhovoru. Má revíziu vstupu, aby staršia úloha neprepísala novšiu pamäť. Fakty majú normalizované kľúče a deduplikáciu významu so zachovaním negácií; neukladať desiatky parafráz. Pri nedostupnej pamäti nehádať pokračovanie zo súkromného chatu, ale odložiť odpoveď alebo použiť len bezpečný miestny kontext.

Pri súbežnom písaní v dvoch kanáloch sú otázky zodpovedané na tom mieste, kde prišli, ale jedna spoločná revízia kontaktu a krátky zámok pri plánovaní zabránia dvom rovnakým pozvaniam alebo protichodným tvrdeniam. Stav „práve aktívny inde“ potláča automatické pripomínanie, nie odpoveď na novú jeho otázku.

Nové raw ingest payloady majú navrhovanú retenciu 30 dní, normalizované správy 180 dní od poslednej aktivity kontaktu, zhrnutia/fakty sa čistia spolu so zdrojmi. Existujúca historická DB sa pri tomto rollout-e automaticky nemaže; najprv náhľad rozsahu retenčnej migrácie. Pri potvrdenom zmazaní zdroja sa prepočíta zhrnutie aj odvodené fakty. Obsahové logy sa anonymizujú; minimálny audit odoslania a opt-out sa drží oddelene bez textu, aby opätovný import neposlal duplicitnú odpoveď. Žiadosť o vymazanie musí odstrániť aj odvodenú pamäť, nie len riadok správy; rozsah existujúcich retenčných povinností sa preverí pred zapnutím automatického mazania.

## 8. Príjem starších IG správ

Prvé zapnutie spraví **import bez odosielania**. Načíta dostupné stránky konverzácií a dostupné detaily správ, vrátane toho, čo už napísal Marek. Označí staré konverzácie ako naimportované; historická posledná otázka sama nevyvolá hromadné odpovedanie.

- Zachovať `occurred_at`, `ingested_at`, ID správy a poradie. **Potvrdene** zmazané/odvolané správy odstrániť z aktívnej pamäti a prepočítať odvodené fakty. V polling verzii potvrdenie znamená jednoznačnú API udalosť alebo ručné označenie majiteľom; vypadnutie z posledných 20 správ nie je dôkaz zmazania. Úplnú detekciu odvolaní bez príslušnej capability nesľubovať a uviesť to pri stave synchronizácie.
- Počiatočný kurzor je stabilný pre celý import; novoprijaté udalosti počas importu sa nestratia. Po dokončení dobehnú cez oddelenú frontu.
- Chybne alebo neúplne naimportovaný chat zostane zablokovaný pre automatické pokračovanie, kým nevie aspoň posledný relevantný úsek. Stav je viditeľný.
- Rozlišovať „všetko, čo API sprístupnilo“ od „celý životný archív“. Staršie chýbajúce konverzácie možno doplniť oficiálnym exportom od majiteľa, ako samostatný import s náhľadom a deduplikáciou; nie sú súčasťou automaticky garantovaného API importu.
- Po aktivácii odpovedať na nové prichádzajúce správy. Marek môže vybrať konkrétny existujúci otvorený chat na prevzatie; aj vtedy platí skutočné časové okno.
- Ručná odchádzajúca správa z Instagramu zruší čakajúci automatický návrh a nastaví takeover na chat. Automat sa vráti až po vedomom Resume, nie svojvoľne o pár minút.

## 9. Plánovanie odpovedí a limity

Príjem a odosielanie sú oddelené. Nová správa sa uloží hneď, ale odpoveď má perzistentné `due_at`; nesmie držať slučku workera v dlhom `sleep`. Vyžrebovaný čas sa uloží raz, reštart ani ďalší poll ho znovu nelosuje.

Správy poslané rýchlo za sebou sa spoja do jedného ťahu: 20–45 s pokoj od poslednej správy, najviac 90 s od prvej. Nové doplnenie počas dlhšej čakacej doby aktualizuje kontext a zneplatní starý návrh, ale nesmie odkladať odpoveď donekonečna.

Navrhované rozdelenie od príchodu pri voľnom aktívnom dni:

| Situácia | Cieľový odstup |
|---|---|
| Prvá správa / návrat po dlhšej pauze | 15 %: 2–5 min; 55 %: 5–25 min; 25 %: 25–90 min; 5 %: 90–180 min |
| Aktívny obojstranný rozhovor | 70 %: 45–180 s; 25 %: 3–8 min; 5 %: 8–20 min |
| Činnosť s obmedzenou dostupnosťou | Spomaliť podľa spoločného denného bloku; pri spánku či úplnej nedostupnosti odložiť |
| Poďakovanie / „ok“ / emoji | Často bez ďalšieho textu; prípadne jedna primeraná DM reakcia |
| Koniec rozhovoru / „dobrú noc“ | Ukončiť ťah a neotvárať okamžite novú tému |

Žiadna automatická odpoveď skôr než 45 s od ukončenia jeho ťahu. Toto je preferencia produktu, nie technika na obídenie detekcie. Ak by konkrétny schválený typ Meta automatizácie vyžadoval inú odozvu, zosúladiť typ použitia a nastavenie s dokumentáciou pred spustením; neoznačiť automat za človeka len kvôli času.

Navrhované úvodné limity **na jeden IG účet**, vyhodnocované atómovo aj pri súbehu:

| Rozpočet | Strop |
|---|---|
| Textové DM + fotky (každá bublina sa počíta) | 12 / kĺzavá hodina; 60 / deň LA; súčasne 60 / kĺzavých 24 h |
| Jedna konverzácia | 8 odpovedí / hodina; 20 / deň LA aj kĺzavých 24 h |
| Nové kontakty, ktorým odpovedá na ich vstup | 10 / deň LA aj 24 h; nejde o cold outreach |
| Súbežné IG rozhovory | 3; po 15 min ticha sa slot uvoľní |
| Verejné komentárové odpovede | 3 / hodina; 12 / deň LA aj 24 h |
| DM reakcie | 10 / hodina; 40 / deň LA aj 24 h |
| Propagačné URL: Telegram + Linkovne spolu | 2 / deň LA aj 24 h; najmenej 4 h medzi odkazmi |
| Celkové IG zápisové akcie | 20 / hodina; 100 / deň LA aj 24 h |

Sú to horné hranice, nikdy kvóty, ktoré sa majú naplniť. Fotka je DM akcia; odkazová správa čerpá aj DM, linkový a celkový rozpočet. Reakcia čerpá reakčný a celkový rozpočet. Limity sa nemajú potichu zvyšovať kvôli dopytu.

Medzi automatickými zápismi do rôznych IG chatov minimálne 45–120 s podľa uloženého rozvrhu. Fronta prioritizuje odpoveď na otázku, potom pokračovanie DM, až potom reakcie a komentáre. Starším čakajúcim DM rastie priorita; hlučný kontakt nemôže zabrať všetky sloty.

Po dosiahnutí limitu sa práca odloží na najbližší prípustný čas. Ak dovtedy vyprší okno, skončí `expired` s dôvodom v Telepipe; neposiela sa obchádzková správa. Ráno sa celá fronta neodošle naraz. Neprítomnosť voliteľných komentárov/reacts nebrzdí oprávnené DM.

Na úvod Semi bez automatického fallbacku, po overení malá Auto skupina. Postupné zvýšenie rozsahu má vychádzať z výsledkov a zdravia účtu, nie z univerzálneho „warmup“ receptu. Existujúci TG/FV objem sa nemení automaticky.

## 10. Okno, opätovné oslovenie a stories

Pred každým IG odoslaním sa znova overí posledná **oprávnená** prichádzajúca udalosť a deadline. Import, prečítanie, klik na externý odkaz, jej vlastná správa, nákup na Fanvue ani like automaticky neobnovujú IG okno. Reakciu používateľa na starú správu nepovažovať bez potvrdenej platformovej podpory za nové okno. Bez platného času akciu neodoslať.

Organické IG DM: automatická správa po 7 dňoch neodíde. Možno uložiť internú pripomienku alebo čakať, kým človek napíše/opäť odpovie na story. Potom sa nadviaže na skutočnú staršiu tému. Nevytvárať zámienku, že AI práve náhodou na človeka myslela. Prípadné re-engagement na TG/FV je samostatná opt-in funkcia, nie presun nevítanej správy na iný kanál.

Budúca voliteľná pripomienka na podporovanom kanáli: posledný vzájomný rozhovor aspoň 7 dní, nie je aktívny inde, neodmietol kontakt, nie je uzatvorený ani obťažujúci, bez pending otázky, max 1 pokus / 14 dní. Ignorovanie = ďalšie proaktívne oslovovanie zastaviť, kým nepríde jeho správa. Výber týždňa a témy vychádza zo spoločnej pamäte. Táto funkcia je v prvej verzii vypnutá.

| Udalosť stories | Správanie |
|---|---|
| Emoji odpoveď prišla ako DM s vlastným ID | Väčšinou len reakcia na tú správu, nie nová predajná konverzácia. |
| Text alebo otázka k story | Bežný DM ťah s kontextom konkrétnej story. |
| Samotný like story, bez DM správy | Žiadna vymyslená DM reakcia; nepovažovať za povolenie začať chat. |
| Mention v cudzej story | Odlišný typ; reagovať len pri známom kontexte a podporovanej akcii, štandardne ručné posúdenie. |
| Story už expirovala a obsah nie je dostupný | Použiť iba doložený popis z vlastného archívu; nevymýšľať, čo bolo na obrázku. |
| Odpoveď je len spam, urážka alebo nebezpečný obsah | Bez srdiečka; prípadne odovzdať Marekovi. |

Pre pozitívne emoji story-DM navrhujem 75–90 % výber reakcie, s jedným uloženým výberom na udalosť. Oneskorenie: 20 % 2–10 min, 60 % 10–120 min, 20 % ďalší aktívny blok. „Zajtra“ len ak je to stále v platnom okne; inak bez reakcie. Najviac jedna automatická reakcia na udalosť a tri na kontakt za deň; séria desiatich emoji nie je desať potrebných akcií. Neskoršia normálna správa zruší zbytočnú čakajúcu reakciu a dostane prednosť.

## 11. Verejné komentáre a lajky

Verejný kontext nikdy nedostane súkromnú pamäť DM, platby ani zistenia z ostatných kanálov. Nehovoriť verejne „včera si mi písal…“. Odpoveď pracuje s komentárom, parent komentárom, popisom príspevku a iba doloženým obsahom média.

Výber nie je mechanické „každý tretí“. Najprv sa odstráni spam, duplicity, vlastné komentáre, už ručne vybavené, obťažovanie a obsah nevhodný na verejnú reakciu. Zo zvyšných je cieľ približne 20–40 % odpovedí v dlhšom horizonte, vždy pod absolútnym stropom. Pri nízkom počte to nie je povinné percento.

| Komentár | Predvolený výber | Tvar |
|---|---|---|
| Zmysluplná otázka k príspevku | Vysoká priorita, cca 80 % | Krátka vecná odpoveď, ak pozná odpoveď |
| Vtip / konkrétny postreh | Cca 45 % | Reakcia na pointu, prípadne jedna relevantná otázka |
| Bežný kompliment | Cca 20 % | Krátke poďakovanie alebo emoji |
| Samotné pozitívne emoji | Cca 10 % | Jedno primerané emoji alebo bez odpovede |
| Opakovaná tá istá fráza od rovnakého účtu | Znížená až nulová | Neodmeňovať spam väčším počtom reakcií |
| Spam, výhražka, obťažovanie, žiadosť o súkromné údaje | 0 % automatických odpovedí/lajkov | Review podľa závažnosti |

Percentá sú počiatočné váhy. Nad nimi je spoločný výber 20–40 % oprávnených komentárov a pevné limity; zrozumiteľná otázka má prednosť pred desiatimi komplimentmi. Výber sa uloží raz, inak by opakované losovanie časom odpovedalo všetkým.

Oneskorenie odpovede 15 min–6 h podľa dostupnosti a priority; rozostup medzi verejnými odpoveďami aspoň 10–30 min. Automaticky nedobiehať komentáre staršie ako 48 h. Najviac jedna automatická odpoveď na pôvodný komentár; nová nadväzujúca otázka má nové ID, môže dostať odpoveď, ale stále platí limit najviac dvoch automatických odpovedí tomu istému účtu pod jedným príspevkom za deň. Žiadny propagačný link vo verejnej odpovedi.

**Lajkovanie komentárov je zatiaľ vypnuté kvôli nepodporenému aktuálnemu prihlasovaciemu setupu.** Ak neskôr oficiálne sprístupníme požadovanú capability: 85–90 % iba vhodných pozitívnych komentárov, oneskorenie 10 min–12 h, max 10/h a 50/deň aj 24 h, spoločný 100/deň rozpočet. Percento nie je povinnosť dobehnúť tisíc komentárov. Like a odpoveď nie sú vždy automaticky pár; rozhoduje význam, nie nafukovanie interakcií. Žiadne lajkovanie vlastných alebo negatívnych/škodlivých komentárov len kvôli percentu.

## 12. Odkazy a jedna fotka

Povolené ciele sú presné adresy uložené majiteľom: Telegram profil a Linkovne profil modelky. Chýbajúca adresa = nič sa nevymyslí. Pri tejto revízii je IG `telegram_handle` prázdny; pri implementácii treba vyplniť overený cieľ. LLM vracia zámer `invite_telegram` alebo `invite_linkpage`, nie ľubovoľnú URL. Finálnu adresu vloží server až po rezervácii rozpočtu.

- Dva linky spolu na IG účet za deň LA aj kĺzavých 24 h, odstup aspoň 4 h. Jedna správa smie mať jeden povolený cieľ.
- Návrh: najviac jeden propagačný link na overeného človeka za celý IG vzťah. Pred potvrdením sa limit vedie na jeho scoped IG ID; zlúčenie prenesie históriu a obmedzenie nezresetuje.
- Výber cieľa podľa výslovnej otázky človeka a konfigurácie; nikam nepozývať automaticky pri každom komplimente. Bez relevancie zostáva rozpočet nevyužitý.
- Keď už odkaz má, môže stručne odkázať na skoršiu správu bez opätovnej URL. Najviac raz za 24 h a len ako odpoveď na jeho novú relevantnú otázku; opakovaný nátlak ukončiť hranicou, nie opakovaným predajom.
- Po vyčerpaní **interného URL rozpočtu** je podľa ďalšieho pokynu Mareka povolený zámer `point_to_highlights`. Nie pevná anglická veta: generátor dostane tento význam spolu s personou, jazykom, celou relevantnou históriou a poslednými vlastnými formuláciami; text napíše aktuálnym štýlom Simony, bez diakritiky a bez povinného emoji. Iba ak je v konfigurácii potvrdené, že tam jej odkaz skutočne je; nenazývať konkrétny výber vymysleným názvom. Žiadna vložená či zakódovaná URL.
- Zmienka o Highlights, bio aj pripomenutie už poslaného odkazu zdieľajú limit **jedného textového pripomenutia na kontakt za 24 h a najviac dvoch za 7 dní**. Musí mať dôvod v jeho aktuálnej správe; nikdy ako automatický nudge. Po odmietnutí pozvania už žiadne. Zmienka spotrebuje normálny DM a celkový rozpočet, iba URL rozpočet nie. Neobíde expirované okno, obsahové pravidlá, opt-out, limit DM ani zásah Meta. Ak nemáme dôvod, pokračuje bežný rozhovor bez pozvania.
- Ručne vložené odkazy z importu sa započítajú do histórie kontaktu; aktuálne ručné odoslania do denného rozpočtu. Ak pôvod alebo stav nevieme, automatický druhý odkaz sa nepovolí.

Fotka: **návrh je jedna za celý IG vzťah s kontaktom**, nie denne a nie po každom novom sedení. Iba zo schváleného SFW albumu konkrétnej modelky, s oprávnením na použitie; nepreposielať cudzie fotky. Žiadny hlas, video ani automatické explicitné médium na IG.

Môže prísť pri primeranej žiadosti o bežnú fotku alebo dlhšej obojstrannej konverzácii (orientačne aspoň šesť zmysluplných ťahov), ak sa hodí ku kontextu. Nie je povinnou odmenou za počet správ. Prijatá jeho fotka sama osebe nespúšťa protifotku. Najprv dostupnosť média, limit, vhodnosť a platné okno; až potom text, ktorý prípadnú fotku ohlasuje. Neodoslané médium sa nesmie v pamäti označiť ako poslané. Neisté doručenie drží rezerváciu až do overenia.

## 13. Štýl, nálada a hranice rozhovoru

Zachovať dnešný slovník a rytmus TG, nie doslova všetky jeho funnel pravidlá. IG môže mať jednu až dve krátke vety, niekedy samotnú vhodnú reakciu. Otázka sa pridáva vtedy, keď dáva zmysel, nie na konci každého ťahu. Odpoveď musí najprv reagovať na to, čo človek skutočne napísal. Plánovač vyberá **zámer a obmedzenia**, generátor vytvára konkrétne znenie; pozvania, pripomenutia, hranice, poďakovania ani opravy preklepov nie sú pevné textové makrá. Aplikujú sa existujúce pravidlá Simony pre slang, interpunkciu, dĺžku, jazyk a text bez diakritiky. Normalizácia sa netýka URL, jednorazových kódov a presných identifikátorov.

- Neopakovať otváracie frázy, otázky ani opakované ospravedlnenia. Kontrola posledných 10–20 vlastných odpovedí a otvorených tém, aj naprieč overenými kanálmi.
- Pri odklone/odmietnutí si pamätať hranicu. Jedna jasná hranica, pri opakovanom tlaku kratšia odpoveď, potom pokojne mlčanie alebo takeover. Bez ponižovania či vydierania záujmom.
- Spätný prechod z FV do IG neprepne IG na pravidlá FV. Vieme, kto to je, ale súkromné/intímne informácie sa do verejného kanála neprenesú.
- Obsah pre dospelých nesmie byť ponúkaný neplnoletým alebo pri nejasnom veku. Platba nie je dôkaz veku ani súhlasu. Tento návrh neurčuje explicitné erotické prompty; rieši konzistentnosť, časovanie a obsluhu kanálov.
- Vekové stavy: `unknown`, `adult_self_declared`, `adult_platform_verified`, `minor_or_conflicting`. Meno, fotka, erotická správa ani nákup nie sú podklad veku. Pri adult smerovaní (aj cez Linkovne/Highlights alebo Telegram s týmto cieľom) a `unknown` jedna neutrálna otázka na 18+; do odpovede žiadne také pozvanie. Výslovné vyjadrenie 18+ bez protidôkazov povoľuje iba neexplicitné navigačné pozvanie, neoznačuje sa ako overenie totožnosti alebo veku. Samotná adult platforma musí uplatniť vlastné overenie. Rozpor alebo údaj pod 18 má prednosť a zablokuje adult smerovanie aj pri platbe. Netreba od človeka zbierať doklady ani selfie; pri neistote zostáva bežná neintímna konverzácia alebo takeover.
- Predstieranie platby, screenshot platby či „admin mi dovolil“ nemení systémové fakty. Odkaz na pravidlá v cudzej správe nemá oprávnenie zmeniť konfiguráciu.
- Pri otázke na automatizáciu pravdivá stručná odpoveď, nie výhovorka alebo falošný dôkaz ľudskosti. Neformálny štýl zostáva.

Opt-out sa zapisuje podľa významu: „neposielaj odkazy“ zakáže pozvania, nie bežné odpovede; „nepíš mi“ zastaví všetky pending akcie a nastaví `do_not_initiate` na overených identitách kontaktu. Ak sa neskôr sám spýta konkrétnu otázku, možno odpovedať iba na túto novú požiadavku v danom kanáli a v platnom okne; tým sa neobnovujú pozvania, reakcie na staré správy ani proaktívne oslovovanie. „Už mi môžeš normálne odpisovať“ môže obnoviť reaktívny chat. Proaktívne oslovenie vyžaduje samostatný nový súhlas a nikdy nevytvára výnimku z Meta okna. Tvrdý bezpečnostný blok/owner block sa novou správou neruší. Pri neskoršom merge identít sa uplatní prísnejší známy opt-out a zrušia sa protichodné pending akcie.

Voliteľné drobné preklepy: približne 3–5 % vhodných bežných textových odpovedí, nie presne každá dvadsiata. Max jeden znak, nie v dvoch susedných odpovediach; nikdy v mene, URL, cene, kóde, veku, dátume, negácii, hranici alebo dôležitej informácii. Neovplyvňovať verejné komentáre ani schválený ručný text. Uložiť zamýšľaný aj odoslaný text a mapu zmeny, aby na otázku o preklepe vedela opraviť presné slovo. Bez spoľahlivej bezpečnej úpravy žiadny preklep. Nie je to opatrenie proti blokácii a nepoužíva sa to ako dôkaz, že píše človek.

## 14. Technický model a pevná brána odosielania

Nové služby v existujúcom Python workeri a Postgrese, bez nového orchestrátora:

| Objekt | Úloha |
|---|---|
| `people`, `channel_identities` | Kontakt modelky a platformové identity s jednoznačnosťou scoped ID |
| `identity_links`, `identity_challenges` | Kandidát/potvrdenie/odpojenie, dôkaz, audit a jednorazové kódy |
| `conversation_events` | Normalizovaný register odkazujúci aj na existujúce tabuľky správ; čas, typ, kanál, pôvod, dedupe |
| `person_facts`, `person_summaries` | Fakty so zdrojmi, verzované zhrnutia a oprávnenie na použitie v kontexte |
| `model_day_state` | Jeden rozvrh a stabilný tón dňa |
| `conversation_state` | Revízia, opt-out, takeover, posledné inbound/outbound, okno a pravidlá kontaktu |
| `scheduled_actions`, `action_attempts` | Trvalá fronta, rezervácia, stav doručenia a dôvod odkladu/zastavenia |
| `action_budgets`, `contact_deliveries` | Atómové hodinové/denné rozpočty, poslané odkazy/fotky |
| `channel_capabilities` | Dokumentovaná + overená podpora reakcií, fotiek, komentárov, lajkov a webhookov |

Všetky objekty nesú `model_id`; cudzie kľúče a unikátne obmedzenia chránia hranice modeliek aj pri chybnom service-role dotaze. RLS viazaná na vlastníctvo účtu. Zmeny identity a rozpočtov cez serverové funkcie s explicitnými grantmi, nie klientským UPDATE. Citlivý obsah, tokeny ani jednorazové kódy nepatria do logov. Existujúce tabuľky zostávajú počas postupnej migrácie; čítanie/zápis cez adaptéry a jasné cutover príznaky, nie dvaja nezávislí odosielatelia.

Tok akcie:

`príjem → deduplikácia → uloženie → klasifikácia → kontext/identita → výber akcie → due_at → schválenie podľa režimu → nová kontrola → rezervácia → odoslanie → potvrdenie/pamäť`

Stavy: `pending`, `waiting_approval`, `ready`, `leased`, `sending`, `sent`, `uncertain`, `retryable`, `cancelled`, `expired`, `blocked`. Každá akcia má `conversation_revision`, `policy_version`, deadline, dedupe kľúč a rezervované rozpočty. Schválenie je viazané na konkrétny obsah a revíziu, nie na chat navždy.

Bezprostredne pred sieťovým zápisom v jednej rozhodovacej vrstve overiť:

1. Účet/kanál pripojený, povolený, správny režim; žiadny globálny pause, takeover, blokácia či opt-out.
2. Capability, platformové okno, oprávnenie na aktuálny thread a korektné typy udalostí.
3. Aktuálnosť kontextu: nepribudla otázka, ručná odpoveď, odvolanie správy, spárovanie iného účtu alebo nová platba meniaca vhodnosť pozvania.
4. Spoločná dostupnosť a povolené časovanie. Pri Semi môže Marek vedome zvoliť Send now mimo harmonogramu; to neobchádza okno, obsahové pravidlá ani limity.
5. Rozpočty, minimum odstupu, idempotencia, jeden link/fotka, validácia textu a médií.

Žiadny LLM nástroj nesmie túto bránu preskočiť. Rezervácia limitu, výber práce a lease musia byť atómové; lease má fencing token, aby starý worker po reštarte neposielal za nový. Vypršaný lease pre `sending` neznamená automatické opakovanie.

Po sieťovom timeoute je výsledok **neistý**, nie automaticky neodoslaný. Najprv reconcile cez platformové ID/echo/dostupnú históriu; ak nemožno rozlíšiť úspech, ručné posúdenie. Žiadne tvrdenie o garantovanom exactly-once pri API bez idempotency podpory. Po potvrdenom zlyhaní obmedzený retry s odstupom, vždy nová kontrola deadline a stavu. Pri páde DB sa neposiela bez rozpočtu a auditu.

Rate-limit odpoveď = rešpektovať `Retry-After` a použiteľné usage hlavičky, prerušiť príslušnú frontu. Odobratý token = zastaviť kanál a vyžiadať reconnect. Permission/capability chyba = zastaviť typ akcie, nie skúšať ho každých 45 s. Blokácia/spam signal = automatické zápisy pauznú a Marek dostane jednu deduplikovanú notifikáciu.

## 15. Príjem udalostí a režimy nasadenia

Prvá verzia vie fungovať s existujúcim pollingom, doplneným stránkovaním, ingest-only režimom, prioritou aktívnych chatov a pomalším čítaním komentárov. Čítanie nesmie byť naviazané len na Auto; v Off možno explicitne povoliť sync histórie bez odpovedí. Poll interval je rozpočet API, nie čas odpovedania.

Ak sa v aktuálnom prístupe nedajú spoľahlivo rozlíšiť story reply, reakcia alebo human echo, príslušná automatizácia zostane vypnutá. Textový chat môže fungovať so známym kontextom. Kontrola najnovšieho stavu tesne pred send znižuje súbeh s ručnou odpoveďou, ale bez eventu nevie zaručiť nulové preteky; preto počiatočný Semi a explicitný takeover.

Webhook adaptér pripraviť pre `messages`, reactions a dostupné komentárové udalosti. Overiť podpis na raw body, tenant routing, replay dedupe, uložiť pred 200 ACK, spracovať až vo workeri. Zapnúť až po overení dostupnosti na konkrétnej appke a účte; endpoint existujúci v kóde sám neznamená doručovanie produkčných webhookov. Polling ostáva reconciler, nie druhý odosielateľ.

Režimy: Off, Sync only, Semi, Auto. Samostatné prepínače DM/stories/comment replies/DM reactions/photo; Comment likes zobrazuje Unsupported pri dnešnom setupu. V Semi žiadny tichý timeout na Auto. Viditeľný dôvod „spí do…“, „čaká na limit“, „okno vypršalo“, „chýba kontext story“, „identita čaká na potvrdenie“.

Testovací účet majiteľa sa viaže na overené scoped IG ID, nie len username. Test mode môže skrátiť čas a otvoriť harmonogram pre tento jeden účet; nikdy neobíde Meta okno, limity, obsahové pravidlá, oprávnenia ani identitu. Samostatný časovo obmedzený prepínač, výrazne viditeľný v Telepipe.

## 16. Scenáre, ktoré musí overiť implementácia

| Situácia | Očakávaný výsledok |
|---|---|
| Úplne nový človek na ktoromkoľvek kanáli | Bežný začiatok, žiadne údajné spoločné zážitky. |
| Známy z IG príde na TG s overeným prepojením | Nadviazanie na poslednú tému, nie nové zoznamovanie. |
| Podobný username dvoch ľudí | Kandidát, žiadna súkromná pamäť. |
| Tvrdí cudzí IG username | Bez potvrdenia nepreniesť históriu. |
| Rovnaký človek zmenil username | Identita podľa ID ostáva, alias sa aktualizuje. |
| Kandidát odmietne prepojenie | Nevracať sa k otázke, oddelený kontakt. |
| Majiteľ zistí nesprávne spojenie | Auditované odpojenie, rebuild summary a zrušenie pending akcií. |
| Prišiel priamo na FV bez IG/TG | Vlastný FV kontakt bez núteného párovania. |
| Píše súčasne na IG aj TG | Odpovedať na miestne otázky, neduplikovať pozvanie a sľuby. |
| Počas čakania pošle tri doplnenia | Jedna odpoveď na aktuálny súhrn. |
| Počas čakania pošle „už nič“ | Zrušiť neaktuálnu otázku/návrh. |
| V noci príde DM | Počkať na dostupnosť; ak okno vyprší, neodoslať. |
| DST zmena / polnoc / worker restart | Žiadne dvojité sloty, reset linku ani nové losovanie due_at. |
| Ráno čaká 80 správ | Postupná fronta pod limitmi, nie dávka odpovedí. |
| Ľudia píšu rýchlejšie než kapacita | Spravodlivé poradie a viditeľné expirácie, bez tichého zvýšenia limitov. |
| Staré ručné IG konverzácie | Import bez automatického dobiehania; nový vstup pokračuje v dostupnej histórii. |
| Staršiu správu API nevrátilo | Označená medzera, žiadne vymyslené spomienky. |
| Marek odpovie v Instagram appke | Zrušiť čakajúci automat, takeover do Resume. |
| V Semi príde nová správa pred schválením | Stará karta je stale, návrh sa aktualizuje. |
| Schválenie po 24 h / po vypnutí / počas takeover | Brána odmietne odoslanie s dôvodom. |
| DM emoji odpoveď na story | Možná jedna oneskorená reakcia, bez povinného textu. |
| Story like bez DM ID | Žiadny vymyslený target ani nová konverzácia. |
| Otázka „kde to je?“ k dostupnej story | Odpoveď z jej doloženého obsahu. |
| Expired story bez popisu | Jedna prirodzená upresňujúca otázka, nie vymyslená lokalita. |
| Desať opakovaných emoji | Debounce a nízky per-contact strop, nie desať lajkov. |
| Komentár s otázkou verzus samotný kompliment | Otázka má vyššiu prioritu, obe stále pod stropmi. |
| LLM vyberie SKIP | Žiadna odpoveď a žiadne opakované losovanie na ďalšom polle. |
| Komentár už ručne vybavený/zmazaný | Zrušiť čakajúcu odpoveď. |
| Tisíc komentárov za hodinu | Platí absolútny strop; neplní sa 90 % za každú cenu. |
| Otázka pod komentárom pokračuje | Doplňujúca krátka reakcia v limite, nie nekonečný verejný chat. |
| Chce Linkovne a rozpočet je voľný | Jeden uložený cieľ; server vloží presnú adresu. |
| Už dostal odkaz a žiada znovu | Odkázať na skoršiu správu bez novej URL. |
| URL limit vyčerpaný, pýta sa kde ju nájde | Ak je to vhodné, raz v limite zmienok nasmerovať na potvrdené Highlights bez URL. |
| URL limit aj bežný DM limit vyčerpaný | Neposlať ani fallback o Highlights; počkať alebo nechať expirovať. |
| Dva súbežné pokusy o posledný denný link | Uspeje len jedna atómová rezervácia. |
| Zmenil deň/username/kanál | História odkazu a fotky sa neresetuje. |
| Chce fotku, schválený album je prázdny | Nesľúbi odoslanie, žiadne vymyslené médium. |
| Už jednu IG fotku dostal | Druhá neodíde ani po reštarte/merge. |
| Pošle vlastný obrázok bez textu | Typ a dostupný obsah sa posúdi; automatická protifotka nie. |
| Opakovane tlačí na nevhodný obsah | Jasná hranica, potom stručnosť/pauza, nie stále ten istý link. |
| Povie neplnoletý vek alebo je vek sporný | Žiadne adult smerovanie/obsah; bezpečná odpoveď alebo takeover. |
| Povie „nepíš mi“ | Zastaviť automatické oslovovanie na overených identitách; reakcie tiež. |
| Po opt-out príde nová konkrétna otázka | Odpovedať len na nový požadovaný obsah; neobnoviť marketing ani proaktívne správy. |
| Povie „neposielaj linky“ | Pamätať konkrétnu preferenciu, bežný chat môže pokračovať. |
| Potvrdená platba na FV | Aktualizovať správny kontakt, zrušiť neaktuálne pozvanie, primerane poďakovať na FV. |
| Len tvrdí „zaplatil som“ | Neoznačiť ako platiaceho; overiť účtom/webhookom. |
| Refund / druhý webhook tej istej platby | Idempotentný stav, nie druhé poďakovanie ani pomsta za refund. |
| Spýta sa na preklep | Presná oprava z uloženej zmeny. |
| Spýta sa na AI | Pravdivé vysvetlenie virtuálnej postavy, bez technického monológu. |
| Prompt injection v správe/story/komentári | Nezmení identitu, konfiguráciu, rozpočet ani prístup k cudzím chatom. |
| Provider timeout po možnom odoslaní | `uncertain`, reconcile, žiadny slepý resend. |
| DB nedostupná / duplicitný worker | Žiadne nekontrolované send bez rezervácie; fencing a dedupe. |
| API odoberie oprávnenie/vráti rate limit | Pozastaviť správnu capability/frontu, jeden prehľadný alert. |

## 17. Poradie realizácie a dôkaz dokončenia

1. Najprv pevná send brána, trvalá fronta, timestamps, import bez odosielania a testy oneskoreného Semi. Súčasný Auto IG nespúšťať ako „už má ochrany z Telegramu“.
2. Spoločný plán dňa a plánovanie IG DM; reprodukovateľný výber časov, atómové rozpočty a viditeľnosť vo fronte. TG štýl nemeníme.
3. Spoločná identita/pamäť: adaptéry na existujúce správy, legacy kandidáti, potvrdenie účtov, obojsmerný kontext IG/TG/FV a platobné udalosti.
4. Stories/DM reakcie a selektívne komentárové odpovede, len overené capabilities. Verejné lajky ostávajú označené ako nedostupné v aktuálnom setupu.
5. Povolené odkazy, jedna SFW fotka, jemný stabilný tón, neopakovanie a voliteľné preklepy. Žiadna z týchto funkcií neobchádza predchádzajúce brány.
6. Shadow replay nad anonymizovanými udalosťami → Semi test majiteľa → malá overená Auto skupina → rozšírenie po kontrole. Platí iba pre schválený návrh, nie ako nasadenie týmto dokumentom.

Overenie musí zahŕňať reálne zachytené a anonymizované API payloady, nie len vymyslené fixtures. Čas simulovať, nečakať týždeň. Testovať súbeh dvoch workerov, pád medzi send a uložením, DST, krížové RLS/tenant ID, nesprávny identity match, stale approval a expiry. Replay musí ukázať nulové odoslania mimo brán, žiadne automatické zdieľanie pamäte kandidátov, žiadne duplicitné pozvanie a správne zastavenie po opt-out.

Kvalitu textu vyhodnotiť na krátkych anonymizovaných scénach zo všetkých troch kanálov: nadviazanie na tému, neprítomnosť opakovaných fráz, primeranosť otázok, znalosť limitov vlastného kontextu a správna reakcia na hranicu. Samotné zelené unit testy nepotvrdzujú, že štýl znie dobre.

Rollback je vypnutie nových odosielateľov/feature flagov a ponechanie ingestu a auditu. Pri neistom doručení nesmie rollback znovu rozoslať starú frontu. Migrácie sú aditívne, staré dáta sa nemažú.

## 18. Voľby autora, ktoré možno pri posúdení upraviť

- Dva linky spolu za celý IG účet, nie na osobu; prísnejšie aj kĺzavých 24 h.
- Po vyčerpaní URL limitu kontextová zmienka o Highlights podľa posledného pokynu Mareka; ostatné brány platia a zmienky majú samostatný strop.
- Jedna IG fotka a jeden propagačný link na kontakt za celý vzťah, nie za deň.
- Číselné úvodné DM/comment/reaction limity a oneskorenia v §9–11.
- Overenie identity pred súkromnou pamäťou; podobnosť username iba kandidát.
- Týždenné automatické organické IG re-engagement sa nezapína; alternatíva je návrat po jeho novej správe.
- Comment likes sa pri aktuálnom Unified Login nesľubujú; neskoršia zmena prístupu je samostatná úloha.
- Stabilný mierny tón a prirodzený štýl, pravdivá identita AI postavy a možnosť zásahu Mareka.

Tieto voľby pochádzajú z návrhu. Následná schválená implementácia zmenila prompty, limity a schému v rozsahu úvodného stavu; IG odpisovanie ostáva Off.

Návrh prešiel samostatným builder-check review. Zapracované otázky: spoločné vypnutie starého párovania a odvodených stavov, pravdivý rozsah detekcie zmazaných správ pri pollingu, vekové stavy pri navigačných pozvaniach a presný návrat po opt-out. Číselné a produktové defaulty sú návrhy autora; nedoriešené schopnosti API sú explicitne vypnuté, nie domyslené.
