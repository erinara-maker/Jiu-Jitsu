#!/bin/bash
set -e

echo "============================================"
echo " Build do Academia CTC - Teste local (Mac)"
echo "============================================"
echo

echo "[1/4] Instalando dependencias do frontend..."
cd frontend
npm install

echo
echo "[2/4] Compilando o frontend (modo desktop)..."
npx ng build --configuration=desktop

echo
echo "[3/4] Copiando frontend para o backend..."
rm -rf ../backend/static
cp -r dist/frontend/browser ../backend/static
cd ..

echo
echo "[4/4] Instalando dependencias Python..."
cd backend
pip install -r requirements.txt

echo
echo "============================================"
echo " Build concluido!"
echo " Para testar, rode:"
echo "   cd backend && python launcher.py"
echo " O navegador abrira em http://localhost:8000"
echo "============================================"
