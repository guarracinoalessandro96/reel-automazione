@echo off
rem "Sveglia" della pubblicazione: la lancia ogni ora l'Utilita' di pianificazione di Windows
rem (attivita' "Reel Alessandro - avvio pubblicazione"). Chiede a GitHub di fare subito il controllo
rem (le esecuzioni programmate di GitHub a volte ritardano). Dal 20/10/2026 non tocca piu' la cartella
rem del progetto (niente pull/commit/push): vedi avvia_pubblicazione.py. Registro in avvia_log.txt.
cd /d "%~dp0"
python avvia_pubblicazione.py > nul 2>> avvia_errori.txt
