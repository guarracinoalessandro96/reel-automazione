"""
FOGLIO "Andamento social" su Google Drive (22/11/2026, Alessandro: un foglio di calcolo aggiornato da solo).
Google Sheets nella cartella "0. Reel Alessandro" (quella che contiene "Video da pubblicare", vedi cartelle.py),
aggiornato da andamento.py a ogni giro su GitHub (ogni ora, dopo ogni reel e intorno a mezzanotte), senza PC.

L'API di Google Sheets NON e' abilitata nel progetto Google (403 "has not been used in project"): si usa solo Drive.
Ogni giro: scarica il foglio come .xlsx (files.export), cambia SOLO i valori delle colonne dati (data e piattaforme) e
le formule delle colonne calcolate di "Visualizzazioni" e "Follower", e lo ricarica sullo STESSO file (files.update con
conversione). Colonne a destra e fogli aggiunti da Alessandro restano (passano per l'xlsx: grafici e cose solo-Sheets
potrebbero semplificarsi). "Riepilogo" si scrive solo se manca. Se il download non riesce non si ricarica niente.
Lo stesso file si ritrova con appProperties andamento=foglio (niente id nel repository pubblico, niente doppioni).
Date: le giornate ufficiali (9:00-9:00 italiane) come settimana/mese della pagina; provvisori in grigio con nota.
Differenza/variazione del totale solo tra giorni con lo stesso numero di piattaforme; totale follower solo con tutte e 4.
  python foglio.py --pc        (prova dal PC: legge docs/andamento/dati.json e aggiorna il foglio)
"""
import datetime, io, json, os, sys

NOME = "Andamento social"
SEGNO = ("andamento", "foglio")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FOGLIO_G = "application/vnd.google-apps.spreadsheet"
SOCIAL = ("YouTube", "Instagram", "TikTok", "Facebook")
ORO, GRIGIO = "FFB703", "8A8A8A"
FMT_DATA = "[$-410]ddd dd/mm/yyyy"       # 410 = italiano: "sab 21/11/2026"
FMT_N, FMT_D, FMT_P = "#,##0", "+#,##0;-#,##0;0", "+0.0%;-0.0%;0.0%"


def _drive(k):
    import statistiche as S
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=S.credenziali(k), cache_discovery=False)


def trova(dr, cartella):
    """Il file del foglio (il piu' vecchio se per sbaglio ce n'e' piu' d'uno), oppure None."""
    q = (f"appProperties has {{ key='{SEGNO[0]}' and value='{SEGNO[1]}' }} and trashed = false")
    f = dr.files().list(q=q, fields="files(id,createdTime)", orderBy="createdTime", pageSize=10).execute()["files"]
    if not f and cartella:
        f = dr.files().list(q=f"name = '{NOME}' and '{cartella}' in parents and mimeType = '{FOGLIO_G}' and trashed = false",
                            fields="files(id,createdTime)", orderBy="createdTime", pageSize=10).execute()["files"]
    return f[0]["id"] if f else None


def _testa(ws, titoli, larghezze):
    from openpyxl.styles import Alignment, Font, PatternFill
    for i, (t, w) in enumerate(zip(titoli, larghezze), 1):
        c = ws.cell(1, i, t)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="7A5200")
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A2"


def _colori(ws, rng):
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Font
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color="1E8E3E", bold=True)))
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"], font=Font(color="D93025", bold=True)))


def _nuovo_vis(wb):
    ws = wb.create_sheet("Visualizzazioni", 0)
    _testa(ws, ["Data", "YouTube", "Instagram", "TikTok", "Facebook", "Totale", "Differenza", "Variazione %"],
           [17, 11, 11, 11, 11, 12, 12, 13])
    _colori(ws, "G2:H5000")
    return ws


def _nuovo_fol(wb):
    ws = wb.create_sheet("Follower", 1)
    _testa(ws, ["Data", "YouTube", "Instagram", "TikTok", "Facebook", "Totale",
                "+ YouTube", "+ Instagram", "+ TikTok", "+ Facebook", "+ Totale"], [17] + [11] * 10)
    _colori(ws, "G2:K5000")
    return ws


def _nuovo_riepilogo(wb):
    from openpyxl.styles import Font
    ws = wb.create_sheet("Riepilogo", 2)
    _testa(ws, ["Periodo", "Dal", "Al", "YouTube", "Instagram", "TikTok", "Facebook", "Totale", "Media al giorno"],
           [30, 15, 15, 12, 12, 12, 12, 13, 15])
    M = "MAX(Visualizzazioni!$A:$A)"
    periodi = [("Ultimi 7 giorni", f"={M}-6", f"={M}"),
               ("Settimana precedente", "=B2-7", "=C2-7"),
               ("Ultimi 30 giorni", f"={M}-29", f"={M}"),
               ("30 giorni precedenti", "=B4-30", "=C4-30"),
               ("Mese corrente", f"=DATE(YEAR({M}),MONTH({M}),1)", f"={M}"),
               ("Stessi giorni del mese prima", "=EDATE(B6,-1)", "=EDATE(C6,-1)")]
    for r, (nome, dal, al) in enumerate(periodi, 2):
        ws.cell(r, 1, nome).font = Font(bold=True)
        ws.cell(r, 2, dal).number_format = FMT_DATA
        ws.cell(r, 3, al).number_format = FMT_DATA
        for j, col in enumerate("BCDE"):
            ws.cell(r, 4 + j, f'=SUMIFS(Visualizzazioni!{col}:{col},Visualizzazioni!$A:$A,">="&$B{r},'
                              f'Visualizzazioni!$A:$A,"<="&$C{r})').number_format = FMT_N
        ws.cell(r, 8, f"=SUM(D{r}:G{r})").number_format = FMT_N
        ws.cell(r, 9, f"=H{r}/(C{r}-B{r}+1)").number_format = FMT_N
    ws.cell(9, 1, "Confronto").font = Font(bold=True, color="7A5200")
    for r, (nome, a, b) in enumerate([("Ultimi 7 giorni / settimana prima", 2, 3),
                                      ("Ultimi 30 giorni / 30 prima", 4, 5),
                                      ("Mese corrente / stessi giorni mese prima", 6, 7)], 10):
        ws.cell(r, 1, nome).font = Font(bold=True)
        for j in range(4, 10):
            L = ws.cell(1, j).column_letter
            ws.cell(r, j, f'=IF({L}{b}=0,"",{L}{a}/{L}{b}-1)').number_format = FMT_P
    _colori(ws, "D10:I12")
    ws.cell(14, 1, "Le giornate sono quelle ufficiali di Instagram, Facebook e YouTube (dalle 9 alle 9, ora italiana). "
                   "TikTok: giornate di TikTok Studio. Grigio = numero provvisorio.").font = Font(italic=True, color=GRIGIO)
    return ws


def _scrivi(ws, righe, colonne_formule, provvisori):
    """righe = [(data, [v1..v4])] dalla piu' recente. Scrive A:E e le formule; pulisce sotto solo le colonne del bot."""
    from openpyxl.comments import Comment
    from openpyxl.styles import Font
    ultima = len(righe) + 1
    for r, (g, valori) in enumerate(righe, 2):
        c = ws.cell(r, 1, datetime.date.fromisoformat(g))
        c.number_format = FMT_DATA
        for j, (s, v) in enumerate(zip(SOCIAL, valori), 2):
            c = ws.cell(r, j, v)
            c.number_format = FMT_N
            prov = g in provvisori.get(s, [])
            c.font = Font(color=GRIGIO, italic=True) if prov else Font()
            c.comment = Comment("provvisorio", "Andamento") if prov and v is not None else None
        for j, (formula, fmt) in enumerate(colonne_formule, 6):
            c = ws.cell(r, j, formula.format(r=r, s=r + 1) if r < ultima or "{s}" not in formula else "")
            c.number_format = fmt
    for r in range(ultima + 1, max(ws.max_row, ultima) + 1):
        for j in range(1, 6 + len(colonne_formule)):
            ws.cell(r, j).value = None
            ws.cell(r, j).comment = None


def aggiorna(k, dati, avvisa=print):
    """Crea o aggiorna il foglio. Mai eccezioni verso chi chiama: stampa e basta (il log e' pubblico: niente id)."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        import openpyxl
        dr = _drive(k)
        cartella = None
        da_pubblicare = k.get("DRIVE_FOLDER_DA_PUBBLICARE") or os.environ.get("DRIVE_FOLDER_DA_PUBBLICARE")
        if da_pubblicare:     # "0. Reel Alessandro" = la cartella che contiene "Video da pubblicare" (cartelle.py)
            cartella = dr.files().get(fileId=da_pubblicare, fields="parents").execute()["parents"][0]
        fid = trova(dr, cartella)
        if fid:
            wb = openpyxl.load_workbook(io.BytesIO(dr.files().export(fileId=fid, mimeType=XLSX).execute()))
        else:
            wb = openpyxl.Workbook()
            wb.remove(wb.active)
        ws_v = wb["Visualizzazioni"] if "Visualizzazioni" in wb.sheetnames else _nuovo_vis(wb)
        ws_f = wb["Follower"] if "Follower" in wb.sheetnames else _nuovo_fol(wb)
        if "Riepilogo" not in wb.sheetnames:
            _nuovo_riepilogo(wb)
        vis, fol, prov = dati.get("visualizzazioni", {}), dati.get("follower", {}), dati.get("provvisori", {})
        riga = lambda tab, g: [tab[g].get(s) for s in SOCIAL]
        _scrivi(ws_v, [(g, riga(vis, g)) for g in sorted(vis, reverse=True)], [
            ('=IF(COUNT(B{r}:E{r})=0,"",SUM(B{r}:E{r}))', FMT_N),
            ('=IF(OR(F{r}="",F{s}="",COUNT(B{r}:E{r})<>COUNT(B{s}:E{s})),"",F{r}-F{s})', FMT_D),
            ('=IF(OR(G{r}="",F{s}=0),"",F{r}/F{s}-1)', FMT_P)], prov)
        _scrivi(ws_f, [(g, riga(fol, g)) for g in sorted(fol, reverse=True)], [
            ('=IF(COUNT(B{r}:E{r})<4,"",SUM(B{r}:E{r}))', FMT_N)] + [
            (f'=IF(OR({L}{{r}}="",{L}{{s}}=""),"",{L}{{r}}-{L}{{s}})', FMT_D) for L in "BCDEF"], {})
        buf = io.BytesIO()
        wb.save(buf)
        media = MediaIoBaseUpload(io.BytesIO(buf.getvalue()), mimetype=XLSX, resumable=False)
        if fid:
            dr.files().update(fileId=fid, media_body=media).execute()
            avvisa(f"Foglio '{NOME}' aggiornato ({len(vis)} giorni)")
        else:
            corpo = {"name": NOME, "mimeType": FOGLIO_G, "appProperties": {SEGNO[0]: SEGNO[1]}}
            if cartella:
                corpo["parents"] = [cartella]
            dr.files().create(body=corpo, media_body=media, fields="id").execute()
            avvisa(f"Foglio '{NOME}' creato ({len(vis)} giorni)")
        return True
    except Exception as e:
        import statistiche as S
        avvisa("Foglio su Drive non aggiornato: " + S.pulito(e)[:200])
        return False


if __name__ == "__main__":
    import statistiche as S
    dati = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "andamento", "dati.json"),
                      encoding="utf-8"))
    aggiorna(S.segreti("--pc" not in sys.argv), dati)
