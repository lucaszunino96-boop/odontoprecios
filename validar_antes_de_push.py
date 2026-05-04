#!/usr/bin/env python3
"""
validar_antes_de_push.py - Correr antes de subir cambios a GitHub.
Si sale todo verde, el Action tiene alta probabilidad de funcionar.
"""

import sys, json, os, ast, re
from pathlib import Path

BASE = Path(__file__).parent
ERRORES = []
ADVERTENCIAS = []

def ok(msg):   print(f"  OK  {msg}")
def falla(msg): print(f"  FALLA  {msg}"); ERRORES.append(msg)
def warn(msg):  print(f"  WARN   {msg}"); ADVERTENCIAS.append(msg)

# 1. SINTAXIS
print("\n[1] Sintaxis de archivos Python")
for fname in ["app.py", "scraper.py", "catalogador.py"]:
    path = BASE / fname
    if not path.exists():
        falla(fname + " no existe")
        continue
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        ok(fname)
    except SyntaxError as e:
        falla(fname + " linea " + str(e.lineno) + ": " + str(e.msg))

# 2. IMPORTS
print("\n[2] Imports catalogador")
try:
    sys.path.insert(0, str(BASE))
    from catalogador import catalogar, clasificar_tokens, _TOKENS_GENERICOS, SINONIMOS_GRUPOS, _norm_sin
    ok("todos los imports OK")
except ImportError as e:
    falla("Import fallido: " + str(e))

# 3. CATALOGADOR
print("\n[3] Funciones catalogador")
try:
    r = catalogar("Composite Filtek Z350 XT 3M A3 4gr")
    assert r.get("marca") == "3m", "marca esperada 3m, got " + str(r.get("marca"))
    assert r.get("tono") == "a3", "tono esperado a3, got " + str(r.get("tono"))
    ok("catalogar() OK: " + str(r))
    t = clasificar_tokens("anestesia anescart forte")
    assert "anescart" in t["especificos"]
    ok("clasificar_tokens() OK: especificos=" + str(t["especificos"]))
except Exception as e:
    falla("Catalogador: " + str(e))

# 4. FORMATO JSON
print("\n[4] productos.json")
json_path = BASE / "productos.json"
if not json_path.exists():
    warn("productos.json no existe - se genera al correr el scraper")
else:
    try:
        data = json.loads(json_path.read_bytes())
        if isinstance(data, dict) and "productos" in data:
            prods = data["productos"]
            meta = data.get("meta", {})
            ok("Formato NUEVO: " + str(len(prods)) + " productos, meta=" + str(meta))
        elif isinstance(data, list):
            prods = data
            warn("Formato VIEJO (lista): " + str(len(prods)) + " productos - OK, app lo soporta")
        else:
            falla("Formato desconocido: " + str(type(data)))
            prods = []
        if len(prods) < 5000:
            falla("Solo " + str(len(prods)) + " productos, esperaba >5000")
        else:
            ok(str(len(prods)) + " productos OK")
        if prods:
            p = prods[0]
            for campo in ["id", "nombre", "precio", "precio_fmt", "tienda_slug", "tienda_nombre"]:
                if campo not in p:
                    falla("Producto sin campo: " + campo)
            ok("Estructura de producto OK")
    except Exception as e:
        falla("Error leyendo JSON: " + str(e))

# 5. APP FORMATO
print("\n[5] app.py lee formato nuevo y viejo")
app_src = (BASE / "app.py").read_text(encoding="utf-8")
if "isinstance(parsed, dict)" in app_src:
    ok("app.py maneja formato nuevo")
else:
    falla("app.py no maneja formato nuevo")
if "lista directa" in app_src or 'productos = parsed' in app_src:
    ok("app.py maneja formato viejo")
else:
    warn("app.py puede no manejar formato viejo")

# 6. GITHUB RAW
print("\n[6] GitHub Raw en app.py")
if "PRODUCTOS_JSON_URL" in app_src:
    ok("URL configurable por env")
else:
    falla("PRODUCTOS_JSON_URL no encontrado en app.py")
if "raw.githubusercontent.com" in app_src:
    ok("URL de GitHub Raw presente")
else:
    falla("URL de GitHub Raw no encontrada en app.py")

# 7. WORKFLOW
print("\n[7] Workflow")
wf_path = BASE / ".github" / "workflows" / "actualizar_precios.yml"
if not wf_path.exists():
    falla("actualizar_precios.yml no encontrado en .github/workflows/")
else:
    wf = wf_path.read_text(encoding="utf-8")
    if "isinstance(d, dict)" in wf:
        ok("COUNT lee formato nuevo")
    else:
        falla("COUNT no lee formato nuevo - va a contar 2 en vez de 15000")
    if "--allow-empty" not in wf:
        ok("sin --allow-empty")
    else:
        warn("tiene --allow-empty - commits vacios")
    if "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" in wf:
        ok("Node.js 24 configurado")
    else:
        warn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 no esta - warnings de Node.js")
    if "RENDER_DEPLOY_HOOK" in wf:
        ok("Render deploy hook presente")
    else:
        warn("RENDER_DEPLOY_HOOK no esta en workflow")

# 8. REQUIREMENTS
print("\n[8] requirements.txt")
req_path = BASE / "requirements.txt"
if not req_path.exists():
    falla("requirements.txt no existe")
else:
    req = req_path.read_text(encoding="utf-8").lower()
    for pkg in ["flask", "rapidfuzz", "beautifulsoup4", "requests", "lxml"]:
        if pkg in req:
            ok(pkg)
        else:
            falla(pkg + " no esta en requirements.txt")

# RESUMEN
print("\n" + "="*50)
if ERRORES:
    print("ERRORES (" + str(len(ERRORES)) + ") - NO pushear hasta resolver:")
    for e in ERRORES:
        print("   * " + e)
else:
    print("SIN ERRORES - listo para pushear y correr Action")
if ADVERTENCIAS:
    print("\nAdvertencias (" + str(len(ADVERTENCIAS)) + "):")
    for w in ADVERTENCIAS:
        print("   * " + w)
print("="*50)

input("\nPresiona Enter para cerrar...")
sys.exit(1 if ERRORES else 0)
