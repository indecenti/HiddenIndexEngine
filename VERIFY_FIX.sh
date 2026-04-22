#!/bin/bash
# Script di verifica che il fix del pacchetto sia funzionante
# Uso: bash VERIFY_FIX.sh

set -e

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "  VERIFICA FIX PACCHETTO GIGANTE"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# Colori
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASS${NC}: $2"
    else
        echo -e "${RED}❌ FAIL${NC}: $2"
        return 1
    fi
}

warn() {
    echo -e "${YELLOW}⚠️  WARNING${NC}: $1"
}

echo "1️⃣  VERIFICA MODIFICHE AL CODICE"
echo "─────────────────────────────────────────────────────────────────────────────"

# Check 1: "-p" rimosso
if grep -q '"-p", str(temp_dir)' editor/build_system.py; then
    echo -e "${RED}❌ FAIL${NC}: Linea '-p, str(temp_dir)' è ancora presente!"
    echo "   File: editor/build_system.py"
    echo "   Questa riga deve essere rimossa!"
    exit 1
else
    check_status $? "Rimosso: '-p', str(temp_dir)"
fi

# Check 2: "--collect-all=engine" aggiunto
if grep -q '"--collect-all=engine"' editor/build_system.py; then
    check_status 0 'Aggiunto: "--collect-all=engine"'
else
    echo -e "${RED}❌ FAIL${NC}: '--collect-all=engine' non trovato!"
    exit 1
fi

# Check 3: Esclusioni autosave presenti
if grep -q '"*.autosave"' editor/build_system.py; then
    check_status 0 'Esclusione: *.autosave'
else
    warn "*.autosave esclusione non trovata"
fi

# Check 4: Validazione EXE size
if grep -q "if exe_size_mb > 500:" editor/build_system.py; then
    check_status 0 'Validazione: EXE <500MB'
else
    warn "EXE size validation non trovata"
fi

# Check 5: Validazione ZIP size
if grep -q "if zip_size_mb > 500:" editor/build_system.py; then
    check_status 0 'Validazione: ZIP <500MB'
else
    warn "ZIP size validation non trovata"
fi

echo ""
echo "2️⃣  VERIFICA FILE DI SUPPORTO"
echo "─────────────────────────────────────────────────────────────────────────────"

# Check files
files=(
    "PACKAGE_SIZE_FIX.md"
    "PACKAGE_SIZE_QUICK_FIX.md"
    "analyze_package_size.py"
    "FINAL_SUMMARY_PACKAGE_FIX.txt"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        check_status 0 "Documentazione: $file"
    else
        warn "File non trovato: $file"
    fi
done

echo ""
echo "3️⃣  STATO BUILD PRECEDENTE"
echo "─────────────────────────────────────────────────────────────────────────────"

if [ -d "build/villa_segreta/1.0/" ]; then
    size=$(du -sh "build/villa_segreta/1.0/" 2>/dev/null | cut -f1)
    echo "📁 Build folder: $size"

    if [ -f "build/villa_segreta/1.0/main.exe" ]; then
        exe_size=$(du -sh "build/villa_segreta/1.0/main.exe" | cut -f1)
        echo "📦 main.exe: $exe_size"

        # Warning se EXE è gigante
        size_mb=$(du -mb "build/villa_segreta/1.0/main.exe" | cut -f1)
        if [ "$size_mb" -gt 500 ]; then
            echo -e "${RED}❌ ATTENZIONE${NC}: main.exe è ancora gigante ($size_mb MB > 500 MB)"
            echo "   Questo significa che il fix potrebbe non essere stato applicato"
            echo "   O che il build non è stato ricreato dopo il fix"
        else
            check_status 0 "EXE size ragionevole (${size_mb}MB < 500MB)"
        fi
    fi
else
    echo "⚠️  No build precedente trovato (normal for first run)"
fi

echo ""
echo "4️⃣  ISTRUZIONI PER VERIFICARE IL FIX"
echo "─────────────────────────────────────────────────────────────────────────────"

echo ""
echo "Step 1: Pulisci build vecchio"
echo "  $ rm -rf build/villa_segreta/1.0/"
echo ""

echo "Step 2: Crea build nuovo"
echo "  $ python test_build_system.py villa_segreta"
echo ""

echo "Step 3: Verifica log"
echo "  $ tail -50 saves/engine.log | grep Validation"
echo "  Devi vedere:"
echo "    [EXE Validation] ✓ Size OK"
echo "    [ZIP Validation] ✓ Size OK"
echo ""

echo "Step 4: Controlla file"
echo "  $ ls -lh build/villa_segreta/1.0/villa_segreta_v1.0.zip"
echo "  Deve essere ~100MB, NON 2.8GB"
echo ""

echo "Step 5: Analizza (se in dubbio)"
echo "  $ python analyze_package_size.py villa_segreta"
echo ""

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✅ VERIFICA COMPLETATA"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Prossimo step: Eseguire 'python test_build_system.py villa_segreta'"
echo ""
