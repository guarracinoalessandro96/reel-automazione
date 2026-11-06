# Frasi sui video - notte del 6/11/2026

## 1. Cosa dicono i numeri

Dati letti stamattina (solo lettura): 284 Shorts con le views di YouTube e 108 reel con le views di Instagram,
presi dallo storico di `stato.json` (tutti i reel dal 23/9 al 6/11).

**YouTube funziona a scatti.** Ogni Short o prende il "giro di prova" (circa 1.000 views) o resta sotto le 300. Dal 29/10
(10 al giorno) su 67 Shorts con almeno 30 ore di vita, 16 hanno preso il giro (24%). Cosa cambia tra i due gruppi:

| Frase | Shorts spinti da YouTube |
|---|---|
| 11-16 parole | **13 su 33 (39%)** |
| fino a 10 parole | 3 su 31 (10%) |
| 17 parole o piu' | 0 su 3 (troppo pochi per dire) |
| due frasi brevi (premessa + colpo) | 28% (contro 18% con una frase sola) |
| ribaltamento "Non e' X. E' Y." | 38% (3 su 8, pochi) |
| in prima persona ("io") | 36% (5 su 14) |
| in seconda persona ("tu") | 17% (3 su 18) |
| con una domanda | 0 su 2 |

Anche l'ora conta: le 06:00 hanno avuto il giro 4 volte su 6, le 12:00 3 su 7, le 08:00, 14:00 e 18:00 mai (0 su 6).

**Instagram**: mediana di 140-150 views a reel e quasi zero salvataggi e condivisioni (in 108 reel: al massimo 2
salvataggi e 1 condivisione). I reel usciti dal gruppo:

- 1.216 - "Il problema non è lasciar andare. È accettare che non tornerà."
- 771 - "Un vincitore è solo uno che ha provato ancora una volta."
- 670 - "Il giorno in cui pianti il seme non è il giorno in cui raccogli il frutto."
- 528 - "Ogni volta che sali di livello, la tua vecchia vita prova a richiamarti. Non rispondere."

Sono tutte frasi che **ribaltano** un'idea conosciuta, con un'immagine concreta (seme, livello), 10-16 parole.
In fondo alla classifica ci sono le frasi corte da poster: "Sì! Puoi farlo." (75 views), "Vivi una vita che
ricorderai." (34), "Il successo è una decisione." (121).

## 2. Il gusto di Alessandro (cartella "Frasi da foto", 16 immagini guardate)

Frasi brevi e semplici, spesso con il "tu", quasi sempre con una svolta: "Non era la fine. Era il cambio scena.",
"E se il rischio più grande fosse rimanere esattamente dove sei?", "È difficile essere costanti quando non hai
nessuno che ti applaude", "Il giorno in cui pianti il seme...". Tono da note del telefono, niente parole difficili.

## 3. Ricerca

- Instagram (Adam Mosseri, 2025): i segnali che contano di piu' sono tempo di visione, like e **invii** (condivisioni
  in privato); per arrivare a chi non ti segue gli invii pesano un po' di piu'.
  https://www.socialmediatoday.com/news/instagram-shares-algorithm-insights-2025/738034/
  -> servono frasi che uno manda a un amico ("questa e' per te", "questo sono io").
- YouTube Shorts: la metrica chiave e' quanti scelgono di guardare invece di scorrere via ("viewed vs swiped away").
  https://buffer.com/resources/the-creators-guide-to-youtube-shorts-analytics
- TikTok: i primi 3-6 secondi decidono. https://www.tiktok.com/business/library/SMB_Creative_Playbook_External.pdf
- Velocita' di lettura media: 238 parole al minuto (Brysbaert 2019, 190 studi): 15 parole si leggono in circa 4 secondi,
  quindi in un reel da 10 s la frase si legge e si rilegge prima del giro successivo.
  https://www.bps.org.uk/research-digest/most-comprehensive-review-date-finds-average-persons-reading-speed-slower
- Le frasi sulla crescita personale migliorano l'immagine di chi le condivide (Frontiers in Psychology 2025): e' il
  motivo per cui la gente le manda e le ripubblica.
  https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1666105/full

## 4. Come sono scritte le 50 frasi nuove (`notte/frasi_nuove.txt`)

- 12-18 parole (quasi tutte 14-17), due frasi brevi: premessa + colpo finale;
- ribaltamenti ("Non sei stanco perché sei debole. Sei stanco perché..."), immagini concrete della sua vita
  (la sveglia presto, una sera a lavorare invece di uscire, capodanno e "un martedi' qualsiasi", il 31 dicembre);
- frasi da mandare a un amico ("Se stai leggendo questo mentre sei stanco...", "Questo è per chi lavora tutto il
  giorno...");
- fine dell'anno: mancano 55 giorni, due frasi usano questa urgenza;
- tutte passano gli stessi filtri dei reel (negativita', palestra, famiglia, confronto, parole cringe, donne, eta')
  e nessuna e' un doppione delle 1.386 frasi del documento (controllo automatico + lettura a mano);
- punteggi onesti da 76 a 99 in `notte/punteggi.txt`, gia' messi in `classifica_frasi.json`.

## 5. Le 10 di oggi (in quest'ordine, una per orario)

1. Una sera a lavorare invece di uscire non ti cambia la vita. Trecento sere sì.
2. Il tuo futuro non cambia a capodanno. Cambia con quello che fai un martedì qualsiasi.
3. Nessuno applaude le mattine in cui ti alzi stanco. Eppure sono quelle a cambiarti la vita.
4. Non sei stanco perché sei debole. Sei stanco perché stai portando avanti qualcosa di grande.
5. Il problema non è la fatica. È abituarsi a una vita più piccola di quella che potresti avere.
6. Un anno fa ci avresti messo la firma per essere dove sei adesso. Ricordatelo nei giorni più duri.
7. Mancano meno di due mesi alla fine dell'anno. Abbastanza per farlo diventare l'anno della svolta.
8. Ho capito che il vero sacrificio non è rinunciare a qualcosa. È rinunciare a chi ero.
9. Ho smesso di chiedermi se ce la farò. Ora mi chiedo cosa posso fare oggi per farcela.
10. La tua vecchia versione non era sbagliata. Ti ha solo portato fin qui. Adesso tocca alla prossima.

**Perche' escono davvero per prime.** `pubblica.py` mette davanti a tutto le frasi di `frasi_forzate.json`, nell'ordine
della lista, finche' non sono uscite (controllo "dal" 2026-11-06T09:00). Con la sola classifica non sarebbero uscite
prima di 5-13 giorni: ci sono ancora 50 frasi delle foto a 100 e 75 frasi a 99 non usate. Le 10 frasi devono pero'
essere nel Google Doc: finche' il coordinatore non lancia `aggiungi_mie.py`, il sistema le salta e va avanti come
oggi (provato). Simulazione con il codice vero e lo stato di stamattina: le 10 escono una per orario esattamente
in quest'ordine, poi si torna alle frasi delle foto.

## 6. Modifica al codice (pubblica.py, una riga)

A parita' di punteggio ora escono prima le frasi da 11-17 parole (39% spinte da YouTube contro il 10% di quelle
corte). Cambia solo l'ordine dentro lo stesso punteggio: nessuna frase viene tolta o aggiunta.

## 7. Da decidere con Alessandro (NON applicato)

Delle 50 frasi delle foto ancora da usare (punteggio 100: passano tutti i filtri per sua scelta del 1/11), 22 vanno
contro le regole che ha dato dopo: dediche alla famiglia ("Non dico spesso grazie, ma una parte di me ti deve tutto"),
amore ("Alcuni amori ti proteggono per tutta la vita..."), odio e negativita' ("I deboli odiano i forti...",
"Niente mi dà fastidio, tranne chi... pugnala alle spalle..."), una al femminile ("Sei diventata la persona...").
Usciranno nei prossimi 5 giorni. Se lui e' d'accordo a sospenderle: `python classifica_frasi.py aggiungi
notte/foto_da_rivedere.txt` (le mette a 0, restano nel documento).

## 8. Comandi per il coordinatore

```
python aggiungi_mie.py notte/frasi_nuove.txt "Notte 6/11/2026"
```
(da lanciare sul PC nella cartella del repo, dopo il merge; deve stampare "AGGIUNTE 50 frasi").
