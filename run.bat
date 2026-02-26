@echo off
setlocal
:: Retorna para a raiz do projeto
cd /d "%~dp0"

:: Define o PYTHONPATH como a raiz (.)
set PYTHONPATH=.

echo ====================================================
echo   Simulador Financeiro - Iniciando Servidores
echo ====================================================

echo 1. Iniciando Backend (FastAPI)...
:: Comando sugerido para forcar reconhecimento do modulo
start "Backend" cmd /c "set PYTHONPATH=.&& python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo 2. Aguardando inicializacao (5s)...
timeout /t 5

echo 3. Iniciando Frontend (Streamlit)...
start "Frontend" cmd /c "set PYTHONPATH=.&& python -m streamlit run frontend/app.py"

echo.
echo Servidores iniciados!
echo ====================================================
pause
