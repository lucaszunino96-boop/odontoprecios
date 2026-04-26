"""
app.py - Servidor web de OdontoPrecio.
Correr con: python app.py
"""

import re, json, os, threading
from flask import Flask, render_template, request, jsonify
from scraper import cargar_productos, correr_scraper, TIENDAS

app = Flask(__name__)

# ─── Cache en memoria ─────────────────────────────────────────
_cache = {"productos": None}

def get_productos():
    if _cache["productos"] is None:
        _cache["productos"] = cargar_productos()
    return _cache["productos"]


def _actualizar_si_es_necesario():
    """
    Corre el scraper en background si los datos tienen mas de 7 dias.
    Se llama automaticamente al arrancar el servidor.
    """
    import datetime
    try:
        from scraper import DB_PATH
        if os.path.exists(DB_PATH):
            mod_time = os.path.getmtime(DB_PATH)
            edad_dias = (datetime.datetime.now().timestamp() - mod_time) / 86400
            if edad_dias < 1:
                print(f"Datos actualizados hace {edad_dias:.1f} dias (menos de 1 dia) — no es necesario scrapear.")
                return
            print(f"Datos tienen {edad_dias:.1f} dias — actualizando precios...")
        else:
            print("No hay datos — scrapeando por primera vez...")

        def _run():
            nuevos = correr_scraper()
            _cache["productos"] = nuevos
            print(f"Auto-actualizacion completada: {len(nuevos)} productos.")
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f"Error en auto-actualizacion: {e}")


# ─── Sinónimos odontológicos ───────────────────────────────────
# Cada grupo: buscar cualquiera encuentra todos los demás
SINONIMOS = [
    {"anestesia", "anescart", "carpule", "mepivacaina", "lidocaina",
     "articaina", "escandicaina", "scandicaine", "mepinor", "mepivastesin",
     "xylestesin", "alphacaine", "ultracaine", "septocaine"},
    {"composite", "resina", "compomero", "filtek", "tetric", "charisma",
     "estelite", "grandio", "gradia", "lumiglass", "restaurador"},
    {"adhesivo", "bond", "primer", "single bond", "optibond", "excite",
     "adper", "scotchbond", "gluma", "clearfil"},
    {"cemento", "ionomero", "ionómero", "glass ionomer", "ketac",
     "fuji", "vitremer", "vitrebond", "relyx", "rely x",
     "maxcem", "multilink", "panavia", "variolink"},
    {"endodoncia", "lima", "limas", "hipoclorito", "edta", "ledermix",
     "gutapercha", "gutta", "conos", "irrigante",
     "protaper", "waveone", "reciproc", "mtwo"},
    {"blanqueamiento", "blanqueador", "peroxido", "whitening",
     "opalescence", "pola", "whiteness"},
    {"impresion", "alginato", "silicona", "vinilpolisiloxano", "vps",
     "putty", "zhermack", "president", "aquasil"},
    {"fresa", "fresas", "turbina", "micromotor", "contraangulo",
     "pieza de mano", "ultrasonido", "cureta"},
    {"bracket", "brackets", "arco", "arcos", "ligadura", "banda", "tubo", "alambre"},
    {"poste", "postes", "perno", "fibra de vidrio"},
    {"sellador", "sellante", "fisuras", "helioseal", "clinpro"},
    {"guante", "guantes", "barbijo", "bioseguridad"},
    {"radiografia", "pelicula", "sensor", "placa radiografica"},
]

# Pre-normalizar sinónimos una sola vez al inicio (no en cada búsqueda)
SINONIMOS_NORM = [
    {re.sub(r"[-./ ]", " ", t).strip() for t in grupo}
    for grupo in SINONIMOS
]

def expandir_query(terminos_set):
    """Dado un set de términos normalizados, agrega sinónimos."""
    expandidos = set(terminos_set)
    for grupo in SINONIMOS_NORM:
        if any(t in grupo or any(t in g for g in grupo) for t in terminos_set):
            expandidos.update(grupo)
    return expandidos


# ─── Motor de búsqueda ─────────────────────────────────────────

def dividir_token(token):
    """
    Divide tokens compuestos en partes para búsqueda flexible.
    z350xt -> ['z350', 'xt']
    p60    -> ['p60']
    3m     -> ['3m']   (empieza con número = unidad completa)
    """
    if token and token[0].isdigit():
        return [token]
    partes = re.findall(r"[a-z]+|[0-9]+", token)
    resultado = []
    i = 0
    while i < len(partes):
        if i + 1 < len(partes) and partes[i].isalpha() and partes[i+1].isdigit():
            resultado.append(partes[i] + partes[i+1])
            i += 2
        else:
            resultado.append(partes[i])
            i += 1
    return resultado

def es_subtoken_valido(token):
    if len(token) <= 1:
        return False
    if token in {"a", "b", "c", "m", "x", "g", "u", "n", "v", "s", "de", "el", "la", "lo", "en", "con", "por", "para"}:
        return False
    return True

def match_token(nombre, nombre_junto, token):
    """
    Retorna score de match:
      200 = match exacto al inicio del nombre (más relevante)
      100 = match exacto como palabra
       50 = match en nombre sin espacios
        1 = substring parcial (menos relevante)
       -1 = no matchea
    """
    patron = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
    if re.search(patron, nombre):
        # Bonus si aparece al inicio
        if nombre.startswith(token) or re.match(r"^" + re.escape(token) + r"(?![a-z0-9])", nombre):
            return 200
        return 100
    if re.search(patron, nombre_junto) or token in nombre_junto:
        return 50
    if token in nombre:
        return 1
    return -1

def calcular_score(nombre_norm, terminos_variantes):
    """
    Calcula relevancia. Retorna -1 si no matchean TODOS los términos.
    Mayor score = más relevante.
    Bonus cuando los términos aparecen juntos y en orden.
    """
    nombre_junto = nombre_norm.replace(" ", "")
    score = 0

    for variantes in terminos_variantes:
        mejor = -1
        for variante in variantes:
            if isinstance(variante, list):
                subtokens = [s for s in variante if es_subtoken_valido(s)]
                if not subtokens:
                    continue
                sub_score, ok = 0, True
                for sub in subtokens:
                    s = match_token(nombre_norm, nombre_junto, sub)
                    if s < 0:
                        ok = False
                        break
                    sub_score += s
                if ok:
                    mejor = max(mejor, sub_score)
            else:
                s = match_token(nombre_norm, nombre_junto, variante)
                if s >= 0:
                    mejor = max(mejor, s)
        if mejor < 0:
            return -1
        score += mejor

    # BONUS 1: todos los términos juntos en orden en el nombre
    # Ej: "3m composite p60" matchea mejor si aparecen en ese orden
    tokens_base = []
    for v in terminos_variantes:
        t = v[0]
        if isinstance(t, list):
            tokens_base.append(t[0])
        else:
            tokens_base.append(t)

    if len(tokens_base) > 1:
        patron_orden = r".*".join(re.escape(t) for t in tokens_base)
        if re.search(patron_orden, nombre_norm) or re.search(patron_orden, nombre_junto):
            score += 100  # Aparecen en el orden correcto

    # BONUS 2: el nombre empieza con el primer término
    if tokens_base and (nombre_norm.startswith(tokens_base[0]) or
        re.match(r"^" + re.escape(tokens_base[0]) + r"(?![a-z0-9])", nombre_norm)):
        score += 50

    # BONUS 3: coincidencia exacta de frase completa
    frase = " ".join(tokens_base)
    if frase in nombre_norm:
        score += 200

    return score

def preparar_query(q):
    q_norm = re.sub(r"[-./ ]", " ", q.lower()).strip()
    q_norm = re.sub(r" +", " ", q_norm)
    terminos_base = q_norm.split()
    terminos_variantes = []
    for t in terminos_base:
        partes = dividir_token(t)
        if len(partes) > 1 and partes != [t]:
            terminos_variantes.append([t, partes])
        else:
            terminos_variantes.append([t])
    base_set = set(terminos_base)
    sinonimos_set = expandir_query(base_set) - base_set
    return terminos_variantes, sinonimos_set


# ─── Rutas ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", tiendas=TIENDAS)


@app.route("/api/buscar")
def buscar():
    q = request.args.get("q", "").strip().lower()

    # Limitar largo de query
    if len(q) < 2:
        return jsonify([])
    if len(q) > 100:
        return jsonify({"error": "Query demasiado larga"}), 400

    productos = get_productos()
    terminos_variantes, sinonimos_set = preparar_query(q)

    resultados_directos = []   # match con términos originales
    resultados_sinonimos = []  # match solo por sinónimo

    for p in productos:
        nombre = re.sub(r"[-./ ]", " ", p["nombre"].lower())
        nombre = re.sub(r" +", " ", nombre)

        # Intentar match directo
        score = calcular_score(nombre, terminos_variantes)
        if score >= 0:
            resultados_directos.append((score, p))
            continue

        # Intentar match por sinónimo
        if sinonimos_set:
            for sin in sinonimos_set:
                nombre_junto = re.sub(r" ", "", nombre)
                patron = r"(?<![a-z0-9])" + re.escape(sin) + r"(?![a-z0-9])"
                if re.search(patron, nombre) or re.search(patron, nombre_junto):
                    resultados_sinonimos.append((1, p))
                    break

    # Ordenar cada grupo por precio
    resultados_directos.sort(key=lambda x: (
        -x[0],                                                    # mayor score primero
        x[1]["precio"] if x[1]["precio"] > 0 else 999_999_999    # menor precio segundo
    ))
    resultados_sinonimos.sort(key=lambda x: (
        x[1]["precio"] if x[1]["precio"] > 0 else 999_999_999
    ))

    # Directos primero, luego sinónimos, máximo 60 resultados
    combinados = resultados_directos + resultados_sinonimos
    return jsonify([p for _, p in combinados[:60]])


@app.route("/api/actualizar", methods=["POST"])
def actualizar():
    """Dispara el scraper en background."""
    def _run():
        nuevos = correr_scraper()
        _cache["productos"] = nuevos
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Actualizando en segundo plano..."})


@app.route("/api/stats")
def stats():
    productos = get_productos()
    por_tienda = {}
    for p in productos:
        t = p["tienda_nombre"]
        por_tienda[t] = por_tienda.get(t, 0) + 1
    return jsonify({"total": len(productos), "por_tienda": por_tienda})


# Arrancar auto-actualizacion al iniciar (funciona tanto con gunicorn como python app.py)
_actualizar_si_es_necesario()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"\n🦷 OdontoPrecio arrancando en puerto {port}...")
    if debug:
        print(f"📡 Abrí tu navegador en: http://localhost:{port}\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
