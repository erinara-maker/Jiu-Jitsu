@echo off
chcp 65001 > nul
echo ============================================
echo  Build do Academia CTC - Executavel Windows
echo ============================================
echo.

:: Verificar se Node.js está instalado
where node > nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Node.js nao encontrado. Instale em https://nodejs.org
    pause
    exit /b 1
)

:: Verificar se Python está instalado
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado. Instale em https://www.python.org
    pause
    exit /b 1
)

echo [1/5] Instalando dependencias do frontend...
cd frontend
call npm install
if %errorlevel% neq 0 ( echo ERRO no npm install & pause & exit /b 1 )

echo.
echo [2/5] Compilando o frontend (modo desktop)...
call npx ng build --configuration=desktop
if %errorlevel% neq 0 ( echo ERRO no build do Angular & pause & exit /b 1 )
cd ..

echo.
echo [3/5] Copiando frontend para o backend...
if exist backend\static rmdir /s /q backend\static
xcopy /E /I /Y frontend\dist\frontend\browser backend\static
if %errorlevel% neq 0 ( echo ERRO ao copiar arquivos & pause & exit /b 1 )

echo.
echo [4/5] Instalando dependencias Python...
cd backend
python -m pip install -r requirements.txt
python -m pip install pyinstaller
if %errorlevel% neq 0 ( echo ERRO no pip install & pause & exit /b 1 )

echo.
echo [5/5] Gerando o executavel...
python -m PyInstaller jiujitsu.spec --clean
if %errorlevel% neq 0 ( echo ERRO no PyInstaller & pause & exit /b 1 )
cd ..

echo.
echo ============================================
echo  Pronto! Executavel gerado em:
echo  backend\dist\Academia CTC.exe
echo ============================================
echo.
echo Copie o arquivo "Academia CTC.exe" para onde quiser.
echo O banco de dados (jiujitsu.db) sera criado na mesma pasta do .exe.
echo.
pause
