@echo off
echo ========================================
echo   FORGIALEAN - DEPLOY SICURO CON BACKUP
echo ========================================
echo.

echo [1/4] Backup database locale...
python backup_db.py
if errorlevel 1 (
    echo ERRORE: Backup fallito!
    pause
    exit /b 1
)
echo.

echo [2/4] Aggiunta file al commit...
git add .
echo.

echo [3/4] Commit automatico...
set /p commit_msg="Messaggio commit (premi Invio per default): "
if "%commit_msg%"=="" set commit_msg=update app with auto-backup
git commit -m "%commit_msg%"
if errorlevel 1 (
    echo Nessuna modifica da committare.
    pause
    exit /b 0
)
echo.

echo [4/4] Push su GitHub...
git push
if errorlevel 1 (
    echo ERRORE: Push fallito!
    pause
    exit /b 1
)
echo.

echo ========================================
echo   DEPLOY COMPLETATO CON SUCCESSO!
echo   Il backup e' stato salvato su GitHub
echo   Streamlit Cloud sta facendo redeploy...
echo ========================================
pause
