@echo off
title OdontoPrecio
echo.
echo  ==========================================
echo   Instalando dependencias...
echo  ==========================================
pip install flask requests beautifulsoup4 lxml curl_cffi -q

if exist productos.json (
    echo.
    echo  ==========================================
    echo   Datos encontrados. Iniciando servidor...
    echo   Para actualizar precios usa: ACTUALIZAR_PRECIOS.bat
    echo  ==========================================
) else (
    echo.
    echo  ==========================================
    echo   Primera vez: descargando productos...
    echo   Esto puede tardar 30-40 minutos.
    echo  ==========================================
    python scraper.py
)

echo.
echo  ==========================================
echo   Abriendo OdontoPrecio en el navegador...
echo   Ingresa a: http://localhost:5000
echo  ==========================================
echo.
start http://localhost:5000
python app.py
