@echo off
title Actualizando precios...
echo.
echo  Actualizando precios de todas las distribuidoras...
echo  Esto puede tardar unos minutos.
echo.
pip install curl_cffi -q
python scraper.py
echo.
echo  Listo! Precios actualizados.
pause
