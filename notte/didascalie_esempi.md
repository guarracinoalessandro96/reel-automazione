# Didascalie, titoli e hashtag: cosa cambia dal 6/11/2026 (area COPY)

Codice: `didascalie.py` (nuovo, solo funzioni semplici), `pubblica.testo_breve` / `youtube_upload` /
`instagram_upload`, `tiktok_prepara.pulisci`. Interruttori: `pubblica.DIDASCALIE_NUOVE` (False = didascalie di prima),
`pubblica.PROVA_IG` (False = niente reel di prova). Ogni parte nuova, se va in errore, torna da sola a quella di prima.

## Cosa dicono le piattaforme (fonti)

- **Instagram - ricerca**: Instagram confronta quello che si cerca con nomi, bio, **didascalie**, hashtag e luoghi;
  le parole chiave vanno nella didascalia, non nei commenti.
  https://about.instagram.com/blog/announcements/break-down-how-instagram-search-works ,
  https://transparency.meta.com/features/explaining-ranking/ig-search/
- **Instagram - hashtag**: da dicembre 2025 al massimo **5 hashtag** per post e reel (Mosseri: pochi e specifici
  funzionano meglio). https://www.socialmediatoday.com/news/instagram-implements-new-limits-on-hashtag-use/808309/ ,
  https://www.businesstoday.in/technology/news/story/no-more-hashtag-stuffing-instagram-limits-hashtag-usage-to-just-5-per-reel-and-post-507444-2025-12-19
- **Instagram - API (documentazione ufficiale Meta)**: `POST /<IG_ID>/media` per i REELS accetta `trial_params`
  (oggetto con `graduation_strategy` = `MANUAL` o `SS_PERFORMANCE`, solo con `media_type=REELS`), `thumb_offset`
  (millisecondi, predefinito 0 = primo fotogramma; ignorato se c'e' `cover_url`) e `share_to_feed`.
  I reel di prova sono "mostrati solo a chi non ti segue". Changelog: Trial Reels nella Content Publishing API dal
  3/12/2025, per tutte le versioni. Nessun campo per rileggere se un reel e' "di prova".
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media ,
  https://developers.facebook.com/docs/instagram-platform/content-publishing ,
  https://developers.facebook.com/docs/instagram-platform/changelog ,
  https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-media
- **Reel di prova - requisiti (fonti non ufficiali, discordanti)**: account pubblico e professionale; alcune guide
  parlano di 1.000 follower (Instagram di Alessandro oggi: 126). Mosseri: di solito hanno meno portata dei reel normali
  perche' non partono dai follower. Il passaggio ai follower non si comanda dall'API.
  https://www.ayrshare.com/docs/apis/post/social-networks/instagram , https://superprofile.bio/guides/instagram-trial-reels ,
  https://postfa.st/blog/instagram-trial-reels
- **Reel di prova - Instagram (guida ufficiale per i creator)**: mostrati prima a chi non ti segue; finche' non li
  condividi con tutti non sono visibili alle altre persone sul profilo, solo dopo vanno nella griglia e ai follower
  (feed e tab Reels); con la condivisione automatica Instagram decide in base alle visualizzazioni delle prime 72 ore.
  https://creators.instagram.com/blog/instagram-trial-reels
- **Reel di prova - errori (Metricool)**: un account non idoneo puo' ricevere dall'API lo stesso messaggio del limite
  ("You reached maximum number of trial reels..."), anche sopra i 1.000 follower se Instagram non ha attivato la
  funzione per l'account. https://help.metricool.com/es/how-to-publish-instagram-trial-reels-in-metricool-q27tj
- **YouTube - #Shorts**: YouTube consiglia #Shorts "nel titolo o nella descrizione"; un video verticale fino a 3 minuti
  e' uno Short anche senza. https://www.socialmediatoday.com/news/youtube-provides-new-overview-of-shorts-for-creators-answers-common-shorts/597446 ,
  https://miraflow.ai/blog/youtube-shorts-hashtags-2026-do-they-still-matter
- **YouTube (Centro assistenza)**: hashtag pertinenti al video (quelli fuori tema possono far togliere il video), fino
  a 3 hashtag della descrizione appaiono vicino al titolo, oltre 60 hashtag vengono ignorati tutti.
  https://support.google.com/youtube/answer/6390658
- **YouTube Shorts - titoli (guide 2025-2026)**: nel feed si leggono circa i primi 40 caratteri, parole chiave
  all'inizio, massimo 100. https://vidiq.com/fr/blog/post/youtube-shorts-titles ,
  https://www.tunepocket.com/youtube-shorts-video-titles/
- **TikTok (Creator Academy)**: la ricerca usa didascalia, testo sul video e parole dette; caricare la didascalia di
  parole o hashtag poco pertinenti "puo' lavorare contro di te" (spam).
  https://www.tiktok.com/creator-academy/article/Getting-discovered-with-Search
- **Facebook (Meta, aprile 2025)**: meno distribuzione a chi usa didascalie lunghe e piene di hashtag o scollegate dal
  video; Meta for Creators (14/7/2025): didascalie e hashtag pertinenti, senza link, poche maiuscole, non piu' di
  5 hashtag. https://about.fb.com/news/2025/04/cracking-down-spammy-content-facebook/ ,
  https://creators.facebook.com/blog/combating-unoriginal-content

## Le scelte

1. **La frase in prima riga** (prima c'era "Giorno X/365"): e' quella che si legge nell'anteprima di Instagram e
   TikTok e contiene le parole che la gente cerca. "Giorno X/365" resta, in terza riga.
2. **Una riga di ricerca presa dalla frase stessa**, in italiano naturale: "Frasi motivazionali sulla costanza e sul
   lavoro." (22 argomenti riconosciuti: disciplina, costanza, sacrificio, obiettivi, futuro, lavoro, sogni, successo,
   determinazione, mentalita', crescita personale, forza di volonta', pazienza, coraggio, abitudini, impegno,
   imprenditoria, rispetto, lealta', cambiamento, vita, tempo). Su TikTok sostituisce le stesse 5 parole fisse che
   finivano su OGNI video (rischio "spam" per TikTok).
3. **4 hashtag pertinenti** (limite Instagram 5): #frasimotivazionali + quelli delle parole della frase + uno a giro.
   Mai #palestra, mai #citazioni (non sono citazioni di altri).
4. **YouTube**: titolo = la frase INTERA + 1 hashtag + #shorts, ma solo quello che ci sta nei 100 caratteri
   (revisione 6/11: prima 23 titoli su 120 tagliavano la fine della frase con "…" per far posto all'hashtag; ora
   solo le frasi che da sole superano 100 caratteri, 3 su 120). Ordine: frase + hashtag + #shorts; se non ci sta,
   frase + hashtag (#shorts e' comunque in descrizione: YouTube chiede #Shorts "nel titolo o nella descrizione");
   se non ci sta, frase + #shorts; poi la frase da sola. L'hashtag che non entra nel titolo va in descrizione.
   L'hashtag ora viene dalla frase molto piu' spesso (prima era a caso se la frase non diceva
   "disciplina/lavoro/..."); descrizione con la stessa struttura (frase, riga di ricerca, Giorno X/365, #shorts +
   2 hashtag). Lingua it, categoria 22, "non per bambini", programmazione all'ora esatta: invariati.
5. **Instagram - copertina**: per i reel da 10 s (tutti, oggi) la copertina era il primo fotogramma. Ora si sceglie
   il fotogramma piu' nitido e ben esposto CON IL VISO (la frase c'e' sempre): vedi
   `C:\Users\User\reel-wt\anteprime\copy_copertina_dieci.jpg`.
6. **Instagram - reel di prova: pronti ma SPENTI** (`PROVA_IG = False`, revisione 6/11). Il "si'" di Alessandro
   c'era solo nel testo del lavoro, non in un suo messaggio: si accendono solo dopo un suo si' esplicito.
   Cosa deve sapere prima di dire si': i reel di prova li vede solo chi NON lo segue; finche' sono di prova **non
   compaiono sul suo profilo e non arrivano ai suoi follower** (sembrera' che manchino dei reel). Se nelle prime
   72 ore vanno bene, Instagram li pubblica da solo per tutti (SS_PERFORMANCE) e allora finiscono sul profilo.
   Come funzionerebbero accesi: 5 reel su 10 (orari alterni che si scambiano ogni giorno), mai i parlati/momenti,
   solo con il brano di Instagram. Partono da soli solo quando servono:
   - Instagram con almeno 200 follower (`docs/follower.json`, oggi 126: secondo le guide sotto i 200 Instagram li
     rifiuta; altre guide dicono 1.000). Quindi, anche accesi, oggi non partirebbero: nessun confronto a breve.
   - Se Instagram ne rifiuta uno (es. "pochi follower"): lo stesso reel esce subito normale (senza il tentativo
     inutile senza share_to_feed) e niente prove per 24 ore.
   - Se un reel di prova esce SENZA il brano di Instagram (`tipo_audio` diverso da `MUSIC`, letto dopo 90 minuti):
     si spengono da soli (si sentirebbe la nostra musica). Si spengono anche se il brano di un reel di prova non si
     riesce a controllare per 24 ore; dopo 6 ore senza controllo si aspetta. Per riaccenderli dopo uno stop:
     spostare `PROVA_IG_DAL` alla data nuova.
   - Se la prova viene rifiutata al momento dell'uscita si rifa' normale solo se Instagram conferma che non e' uscito
     (mai doppio). In stato.json, risultati instagram: `"prova": true/false` e `"prova_rifiutata"` col motivo.
7. **Invariati**: momenti veri e parlati (il loro testo), liste/regole, niente domande per i commenti, niente
   "seguimi", niente autori, niente eta'.

## 10 esempi (generati dal codice, prove offline senza pubblicare)

Data di prova: 6/11/2026 = Giorno 310/365. Gli hashtag "a giro" restano uguali per la stessa frase (stesso reel
riprovato = stessa didascalia).

### 1. Quando la fatica nasce da qualcosa che ami, non pesa più. Diventa libertà.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Quando la fatica nasce da qualcosa che ami, non pesa più. Diventa libertà

#impegno #motivazione #citazioni
```

Dopo (Instagram, TikTok, Facebook):
```
Quando la fatica nasce da qualcosa che ami, non pesa più. Diventa libertà

Frasi motivazionali in italiano sull'impegno e sulla crescita personale.
Giorno 310/365

#frasimotivazionali #impegno #mentalita #frasidivita
```

YouTube dopo - titolo: `Quando la fatica nasce da qualcosa che ami, non pesa più. Diventa libertà. #impegno #shorts`

```
Quando la fatica nasce da qualcosa che ami, non pesa più. Diventa libertà

Frasi motivazionali in italiano sull'impegno e sulla crescita personale.
Giorno 310/365

#shorts #frasimotivazionali #mentalita
```

### 2. Non aspettare che passi la tempesta. Impara a lavorare sotto la pioggia.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Non aspettare che passi la tempesta. Impara a lavorare sotto la pioggia

#lavoro #mentalita #obiettivi
```

Dopo (Instagram, TikTok, Facebook):
```
Non aspettare che passi la tempesta. Impara a lavorare sotto la pioggia

Frasi motivazionali sul lavoro e sul futuro, per ripartire ogni giorno.
Giorno 310/365

#frasimotivazionali #lavoro #motivazione #crescitapersonale
```

YouTube dopo - titolo: `Non aspettare che passi la tempesta. Impara a lavorare sotto la pioggia. #lavoro #shorts`

```
Non aspettare che passi la tempesta. Impara a lavorare sotto la pioggia

Frasi motivazionali sul lavoro e sul futuro, per ripartire ogni giorno.
Giorno 310/365

#shorts #frasimotivazionali #motivazione
```

### 3. Stesso albero, stagione diversa. Ricorda: tutto è temporaneo.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Stesso albero, stagione diversa. Ricorda: tutto è temporaneo

#mentalita #obiettivi #disciplina
```

Dopo (Instagram, TikTok, Facebook):
```
Stesso albero, stagione diversa. Ricorda: tutto è temporaneo

Frasi motivazionali sul futuro e sulla vita, per ripartire ogni giorno.
Giorno 310/365

#frasimotivazionali #motivazione #crescitapersonale #mentalita
```

YouTube dopo - titolo: `Stesso albero, stagione diversa. Ricorda: tutto è temporaneo. #crescitapersonale #shorts`

```
Stesso albero, stagione diversa. Ricorda: tutto è temporaneo

Frasi motivazionali sul futuro e sulla vita, per ripartire ogni giorno.
Giorno 310/365

#shorts #frasimotivazionali #motivazione
```

### 4. Il tempo non cura tutto. Ma insegna a reggere.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Il tempo non cura tutto. Ma insegna a reggere

#disciplina #crescitapersonale #frasidivita
```

Dopo (Instagram, TikTok, Facebook):
```
Il tempo non cura tutto. Ma insegna a reggere

Frasi motivazionali in italiano sul tempo e sulla crescita personale.
Giorno 310/365

#frasimotivazionali #motivazione #crescitapersonale #mentalita
```

YouTube dopo - titolo: `Il tempo non cura tutto. Ma insegna a reggere. #motivazione #shorts`

```
Il tempo non cura tutto. Ma insegna a reggere

Frasi motivazionali in italiano sul tempo e sulla crescita personale.
Giorno 310/365

#shorts #frasimotivazionali #crescitapersonale
```

### 5. Sono fiero della mia nuova versione: sceglie la crescita invece della comodità.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Sono fiero della mia nuova versione: sceglie la crescita invece della comodità

#crescitapersonale #obiettivi #disciplina
```

Dopo (Instagram, TikTok, Facebook):
```
Sono fiero della mia nuova versione: sceglie la crescita invece della comodità

Frasi motivazionali sulla crescita personale e sulla vita.
Giorno 310/365

#frasimotivazionali #crescitapersonale #motivazione #mentalita
```

YouTube dopo - titolo: `Sono fiero della mia nuova versione: sceglie la crescita invece della comodità. #crescitapersonale`
(prima della revisione: `...sceglie la crescita invece della… #crescitapersonale #shorts`)

```
Sono fiero della mia nuova versione: sceglie la crescita invece della comodità

Frasi motivazionali sulla crescita personale e sulla vita.
Giorno 310/365

#shorts #frasimotivazionali #motivazione
```

### 6. La disciplina è scegliere tra quello che vuoi adesso e quello che vuoi di più.  (tema: disciplina)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
La disciplina è scegliere tra quello che vuoi adesso e quello che vuoi di più

#disciplina #obiettivi #crescitapersonale
```

Dopo (Instagram, TikTok, Facebook):
```
La disciplina è scegliere tra quello che vuoi adesso e quello che vuoi di più

Frasi motivazionali sulla disciplina e sulla costanza.
Giorno 310/365

#frasimotivazionali #disciplina #motivazione #crescitapersonale
```

YouTube dopo - titolo: `La disciplina è scegliere tra quello che vuoi adesso e quello che vuoi di più. #disciplina #shorts`

```
La disciplina è scegliere tra quello che vuoi adesso e quello che vuoi di più

Frasi motivazionali sulla disciplina e sulla costanza.
Giorno 310/365

#shorts #frasimotivazionali #motivazione
```

### 7. Ogni sacrificio di oggi è un mattone del mio futuro.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Ogni sacrificio di oggi è un mattone del mio futuro

#sacrificio #futuro #mentalita
```

Dopo (Instagram, TikTok, Facebook):
```
Ogni sacrificio di oggi è un mattone del mio futuro

Frasi motivazionali sul sacrificio e sul futuro, per ripartire ogni giorno.
Giorno 310/365

#frasimotivazionali #sacrificio #futuro #motivazione
```

YouTube dopo - titolo: `Ogni sacrificio di oggi è un mattone del mio futuro. #sacrificio #shorts`

```
Ogni sacrificio di oggi è un mattone del mio futuro

Frasi motivazionali sul sacrificio e sul futuro, per ripartire ogni giorno.
Giorno 310/365

#shorts #frasimotivazionali #futuro
```

### 8. Mi alleno anche quando nessuno guarda, perché la costanza non ha pubblico.  (tema: palestra)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Mi alleno anche quando nessuno guarda, perché la costanza non ha pubblico

#costanza #frasidivita #frasimotivazionali
```

Dopo (Instagram, TikTok, Facebook):
```
Mi alleno anche quando nessuno guarda, perché la costanza non ha pubblico

Frasi motivazionali sulla costanza e sulla disciplina, per ripartire ogni giorno.
Giorno 310/365

#frasimotivazionali #costanza #frasidivita #disciplina
```

YouTube dopo - titolo: `Mi alleno anche quando nessuno guarda, perché la costanza non ha pubblico. #costanza #shorts`

```
Mi alleno anche quando nessuno guarda, perché la costanza non ha pubblico

Frasi motivazionali sulla costanza e sulla disciplina, per ripartire ogni giorno.
Giorno 310/365

#shorts #frasimotivazionali #frasidivita
```

### 9. Ogni cliente soddisfatto è la prova che il lavoro fatto bene paga sempre.  (tema: imprenditore)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Ogni cliente soddisfatto è la prova che il lavoro fatto bene paga sempre

#lavoro #imprenditore #obiettivi
```

Dopo (Instagram, TikTok, Facebook):
```
Ogni cliente soddisfatto è la prova che il lavoro fatto bene paga sempre

Frasi motivazionali sul lavoro e sull'imprenditoria.
Giorno 310/365

#frasimotivazionali #lavoro #imprenditore #crescitapersonale
```

YouTube dopo - titolo: `Ogni cliente soddisfatto è la prova che il lavoro fatto bene paga sempre. #lavoro #shorts`

```
Ogni cliente soddisfatto è la prova che il lavoro fatto bene paga sempre

Frasi motivazionali sul lavoro e sull'imprenditoria.
Giorno 310/365

#shorts #frasimotivazionali #imprenditore
```

### 10. Rispetta te stesso abbastanza da non accontentarti.  (tema: mentalita)

Prima (Instagram, file TikTok/Facebook):
```
Giorno 310/365
Rispetta te stesso abbastanza da non accontentarti

#rispetto #motivazione #citazioni
```

Dopo (Instagram, TikTok, Facebook):
```
Rispetta te stesso abbastanza da non accontentarti

Frasi motivazionali in italiano sul rispetto e sulla crescita personale.
Giorno 310/365

#frasimotivazionali #rispetto #mentalita #frasidivita
```

YouTube dopo - titolo: `Rispetta te stesso abbastanza da non accontentarti. #rispetto #shorts`

```
Rispetta te stesso abbastanza da non accontentarti

Frasi motivazionali in italiano sul rispetto e sulla crescita personale.
Giorno 310/365

#shorts #frasimotivazionali #mentalita
```

## Revisione 6/11/2026: titoli YouTube delle 120 frasi vere piu' recenti (stato.json)

Prima 23 titoli su 120 erano tagliati con "…", ora 3 (solo le frasi che da sole superano 100 caratteri). Tutti i titoli che cambiano (prima -> dopo):

- prima: `Se qualcuno ti tratta come un'opzione, smetti di trattarlo come una… #crescitapersonale #shorts`
  dopo:  `Se qualcuno ti tratta come un'opzione, smetti di trattarlo come una priorità. #crescitapersonale`
- prima: `Il modo in cui le persone ti trattano mostra le loro ferite, non il… #crescitapersonale #shorts`
  dopo:  `Il modo in cui le persone ti trattano mostra le loro ferite, non il tuo valore. #crescitapersonale`
- prima: `Alcune persone non vedono quanto fai per loro. Vedono solo quello che non… #motivazione #shorts`
  dopo:  `Alcune persone non vedono quanto fai per loro. Vedono solo quello che non fai. Non soddisferai mai…`
- prima: `Non mancare mai di rispetto alle persone silenziose: osservano tutto e… #rispetto #shorts`
  dopo:  `Non mancare mai di rispetto alle persone silenziose: osservano tutto e ricordano tutto. #rispetto`
- prima: `Stai rimuginando di nuovo. Respira. Va bene, capirai come gestirla. E anche… #disciplina #shorts`
  dopo:  `Stai rimuginando di nuovo. Respira. Va bene, capirai come gestirla. E anche se non ci riesci, va…`
- prima: `Se vuoi qualcosa che non hai mai avuto, fai qualcosa che non hai mai… #crescitapersonale #shorts`
  dopo:  `Se vuoi qualcosa che non hai mai avuto, fai qualcosa che non hai mai fatto. #crescitapersonale`
- prima: `Non so come finirà la mia storia. Ma non leggerai mai che mi sono… #crescitapersonale #shorts`
  dopo:  `Non so come finirà la mia storia. Ma non leggerai mai che mi sono arreso. #crescitapersonale #shorts`
- prima: `Se ti offrono una grande occasione e non sei sicuro di farcela: accetta… #motivazione #shorts`
  dopo:  `Se ti offrono una grande occasione e non sei sicuro di farcela: accetta, poi impari come si fa.`
- prima: `Se vuoi davvero ottenere qualcosa, devi lavorare sodo. Nessuno costruirà il tuo… #futuro #shorts`
  dopo:  `Se vuoi davvero ottenere qualcosa, devi lavorare sodo. Nessuno costruirà il tuo futuro al posto tuo.`
- prima: `Non esistono scorciatoie. Più difficile del lavoro è svegliarti tra dieci anni… #lavoro #shorts`
  dopo:  `Non esistono scorciatoie. Più difficile del lavoro è svegliarti tra dieci anni nello stesso punto…`
- prima: `Un obiettivo così grande non sarebbe nato dentro di te se non potessi… #obiettivi #shorts`
  dopo:  `Un obiettivo così grande non sarebbe nato dentro di te se non potessi realizzarlo. #obiettivi`
- prima: `Ogni volta che sali di livello, la tua vecchia vita prova a richiamarti.… #frasidivita #shorts`
  dopo:  `Ogni volta che sali di livello, la tua vecchia vita prova a richiamarti. Non rispondere. #shorts`
- prima: `Il giorno in cui pianti il seme non è il giorno in cui raccogli il… #crescitapersonale #shorts`
  dopo:  `Il giorno in cui pianti il seme non è il giorno in cui raccogli il frutto. #crescitapersonale`
- prima: `Non ho ancora vinto. Forse non è il momento. Però ci sto provando con tutto… #disciplina #shorts`
  dopo:  `Non ho ancora vinto. Forse non è il momento. Però ci sto provando con tutto me stesso. #disciplina`
- prima: `La bussola è nata prima dell'orologio. Sapere dove vai conta più del… #crescitapersonale #shorts`
  dopo:  `La bussola è nata prima dell'orologio. Sapere dove vai conta più del tempo che ci metti. #shorts`
- prima: `Alla fine della giornata nessuno sa quanto ti impegni. Per questo devi farlo… #impegno #shorts`
  dopo:  `Alla fine della giornata nessuno sa quanto ti impegni. Per questo devi farlo per te stesso. #impegno`
- prima: `La bussola è nata prima dell'orologio. Sapere dove vai conta più del tempo… #disciplina #shorts`
  dopo:  `La bussola è nata prima dell'orologio. Sapere dove vai conta più del tempo che ci metti. #disciplina`
- prima: `È difficile essere costante senza nessuno che ti applaude. A volte ti… #costanza #shorts`
  dopo:  `È difficile essere costante senza nessuno che ti applaude. A volte ti incoraggi da solo. #costanza`
- prima: `Il tuo potenziale non ha limiti. Finora hai mostrato solo una minima… #crescitapersonale #shorts`
  dopo:  `Il tuo potenziale non ha limiti. Finora hai mostrato solo una minima parte. #crescitapersonale`
- prima: `Alla lunga il sacrificio paga. Il successo dipende da ciò che fai succedere… #sacrificio #shorts`
  dopo:  `Alla lunga il sacrificio paga. Il successo dipende da ciò che fai succedere ogni giorno. #sacrificio`
- prima: `Un giorno i risultati parleranno al posto tuo. E quel silenzio varrà più di… #disciplina #shorts`
  dopo:  `Un giorno i risultati parleranno al posto tuo. E quel silenzio varrà più di mille spiegazioni.`
- prima: `Sono fiero della mia nuova versione: sceglie la crescita invece della… #crescitapersonale #shorts`
  dopo:  `Sono fiero della mia nuova versione: sceglie la crescita invece della comodità. #crescitapersonale`
- prima: `La parte più difficile non è dimenticare. È continuare a vivere con tutto… #disciplina #shorts`
  dopo:  `La parte più difficile non è dimenticare. È continuare a vivere con tutto quello che resta. #shorts`
