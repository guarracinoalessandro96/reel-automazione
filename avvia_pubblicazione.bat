@echo off
rem "Sveglia" della pubblicazione: la lancia l'Utilita' di pianificazione di Windows alle 9:02, 12:02, 15:02, 18:02, 21:02
rem (attivita' "Reel Alessandro - avvio pubblicazione"). Aggiorna avvia.txt e fa push: GitHub parte subito
rem (le esecuzioni programmate di GitHub da sole a volte saltano). Registro in avvia_log.txt (non va su GitHub).
cd /d "%~dp0"
echo %date% %time% avvio >> avvia_log.txt
git pull -q --rebase --autostash >> avvia_log.txt 2>&1
> avvia.txt echo Modificare questo file (commit + push) fa partire subito il controllo di pubblicazione su GitHub.
>> avvia.txt echo Ultimo avvio dal PC: %date% %time%
git add avvia.txt
git commit -q -m "Avvio pubblicazione dal PC" avvia.txt >> avvia_log.txt 2>&1
git push -q >> avvia_log.txt 2>&1 || (git pull -q --rebase --autostash && git push -q) >> avvia_log.txt 2>&1
echo %date% %time% fatto >> avvia_log.txt
