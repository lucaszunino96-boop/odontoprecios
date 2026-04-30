"""
app.py - Servidor web de OdontoPrecio.
Correr con: python app.py
"""

import re, json, os, threading
from flask import Flask, render_template, request, jsonify
from scraper import cargar_productos, correr_scraper, TIENDAS

app = Flask(__name__)

_cache = {"productos": None, "historial": None}

def get_productos():
    if _cache["productos"] is None:
        _cache["productos"] = cargar_productos()
    return _cache["productos"]

def _actualizar_si_es_necesario():
    import datetime
    try:
        from scraper import DB_PATH
        if os.path.exists(DB_PATH):
            mod_time = os.path.getmtime(DB_PATH)
            edad_dias = (datetime.datetime.now().timestamp() - mod_time) / 86400
            if edad_dias < 2:
                print(f"Datos actualizados hace {edad_dias:.1f} dias — no es necesario scrapear.")
                return
            print(f"Datos tienen {edad_dias:.1f} dias — actualizando precios...")
        else:
            print("No hay datos — scrapeando por primera vez...")
        def _run():
            nuevos = correr_scraper()
            _cache["productos"] = nuevos
            try:
                hist = guardar_historial(nuevos)
                _cache["historial"] = hist
            except Exception as e:
                print(f"Error guardando historial: {e}")
            print(f"Auto-actualizacion completada: {len(nuevos)} productos.")
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f"Error en auto-actualizacion: {e}")

# ─── Sinónimos ────────────────────────────────────────────────────────────────
SINONIMOS = [
    {"anestesia", "anescart", "carpule", "mepivacaina", "lidocaina",
     "articaina", "escandicaina", "scandicaine", "mepinor",
     "xylestesin", "alphacaine", "ultracaine", "septocaine", "mepicaton"},
    {"composite", "resina", "compomero", "filtek", "tetric", "charisma",
     "estelite", "grandio", "gradia", "z350", "z250", "p60", "flow"},
    {"adhesivo", "bond", "primer", "optibond", "scotchbond", "gluma", "clearfil"},
    {"cemento", "ionomero", "ionómero", "ketac", "fuji", "relyx",
     "maxcem", "multilink", "panavia", "variolink"},
    {"endodoncia", "lima", "limas",
     "gutapercha", "guttapercha", "guta percha", "gutta percha",
     "puntas de gutapercha", "conos de gutapercha",
     "hipoclorito", "edta", "irrigante",
     "protaper", "waveone", "reciproc", "mtwo",
     "adseal", "ah plus", "sealapex"},
    {"blanqueamiento", "blanqueador", "peroxido", "whitening", "opalescence", "pola"},
    {"impresion", "impresión", "alginato", "silicona", "vinilpolisiloxano",
     "putty", "zhermack", "president", "aquasil"},
    {"fresa", "fresas", "turbina", "micromotor", "contraangulo", "piedra"},
    {"bracket", "brackets", "arco", "arcos", "ligadura", "tubo", "alambre"},
    {"poste", "postes", "perno", "fibra de vidrio"},
    {"sellador", "sellante", "helioseal", "clinpro"},
    {"guante", "guantes", "barbijo", "barbijos", "bioseguridad",
     "descartable", "descartables", "babero", "eyector"},
    {"radiografia", "radiografía", "pelicula", "sensor", "rx"},
    {"yeso", "yesos", "escayola"},
    {"acrilico", "acrílico", "duralay", "protesis", "prótesis"},
    {"banda de matriz", "rollo de matriz", "banda matricial",
     "tofflemire", "palodent", "sectorial"},
]

SINONIMOS_NORM = []
for _grupo in SINONIMOS:
    _grupo_norm = set()
    for _t in _grupo:
        _t_norm = re.sub(r"[-./ ]", " ", _t.lower()).strip()
        _grupo_norm.add(_t_norm)
        _sin_esp = _t_norm.replace(" ", "")
        if _sin_esp != _t_norm:
            _grupo_norm.add(_sin_esp)
    SINONIMOS_NORM.append(_grupo_norm)

STOPWORDS = {"a","b","c","m","x","g","u","n","v","s",
             "de","el","la","lo","en","con","por","para","y","o","e"}

def expandir_query(terminos_set, q_norm_completo):
    terminos_sig = [t for t in terminos_set if t not in STOPWORDS and len(t) > 1]
    es_simple = len(terminos_sig) == 1
    frase_en_grupo = any(
        any(q_norm_completo == g or q_norm_completo in g or g in q_norm_completo
            for g in grupo)
        for grupo in SINONIMOS_NORM
    )
    if not es_simple and not frase_en_grupo:
        return set(terminos_set)
    expandidos = set(terminos_set)
    for grupo in SINONIMOS_NORM:
        if any(t == g or t in g or g in t for t in terminos_set for g in grupo):
            expandidos.update(grupo)
        if frase_en_grupo and any(
            q_norm_completo == g or q_norm_completo in g or g in q_norm_completo
            for g in grupo
        ):
            expandidos.update(grupo)
    return expandidos

def dividir_token(token):
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

def match_token(nombre, nombre_junto, token):
    patron = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
    if re.search(patron, nombre):
        if nombre.startswith(token) or re.match(r"^" + re.escape(token) + r"(?![a-z0-9])", nombre):
            return 200
        return 100
    if re.search(patron, nombre_junto) or token in nombre_junto:
        return 50
    if token in nombre:
        return 1
    return -1

def calcular_score(nombre_norm, terminos_variantes):
    nombre_junto = nombre_norm.replace(" ", "")
    score = 0
    for variantes in terminos_variantes:
        mejor = -1
        for variante in variantes:
            if isinstance(variante, list):
                subtokens = [s for s in variante if len(s) > 1 and s not in STOPWORDS]
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
    tokens_base = [v[0][0] if isinstance(v[0], list) else v[0] for v in terminos_variantes]
    if len(tokens_base) > 1:
        patron_orden = r".*".join(re.escape(t) for t in tokens_base)
        if re.search(patron_orden, nombre_norm) or re.search(patron_orden, nombre_junto):
            score += 100
    if tokens_base and (nombre_norm.startswith(tokens_base[0]) or
        re.match(r"^" + re.escape(tokens_base[0]) + r"(?![a-z0-9])", nombre_norm)):
        score += 50
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
    q_sin_espacios = q_norm.replace(" ", "")
    if q_sin_espacios != q_norm:
        base_set.add(q_sin_espacios)
    sinonimos_set = expandir_query(base_set, q_norm) - base_set
    return terminos_variantes, sinonimos_set

# ─── Historial ────────────────────────────────────────────────────────────────
HIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historial.json")

def cargar_historial():
    if os.path.exists(HIST_PATH):
        try:
            with open(HIST_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_historial(productos_nuevos):
    from datetime import datetime
    hist = cargar_historial()
    hoy = datetime.now().strftime("%Y-%m-%d")
    cambiaron = 0
    for p in productos_nuevos:
        pid = p["id"]
        precio = p["precio"]
        if pid not in hist:
            hist[pid] = []
        if not hist[pid] or hist[pid][-1]["precio"] != precio:
            hist[pid].append({"fecha": hoy, "precio": precio})
            if len(hist[pid]) > 90:
                hist[pid] = hist[pid][-90:]
            cambiaron += 1
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)
    print(f"Historial actualizado: {cambiaron} productos con cambios de precio.")
    return hist

_cache["historial"] = None

def get_historial():
    if _cache["historial"] is None:
        _cache["historial"] = cargar_historial()
    return _cache["historial"]

# ─── Reportes ─────────────────────────────────────────────────────────────────
REPORTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reportes.json")

def guardar_reporte(producto_id, nombre, tienda, precio_actual, comentario, ip):
    from datetime import datetime
    reportes = []
    if os.path.exists(REPORTES_PATH):
        try:
            with open(REPORTES_PATH, encoding="utf-8") as f:
                reportes = json.load(f)
        except Exception:
            reportes = []
    reportes.append({
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "producto_id": producto_id,
        "nombre": nombre,
        "tienda": tienda,
        "precio_actual": precio_actual,
        "comentario": comentario[:200],
        "ip": ip[:20] if ip else ""
    })
    reportes = reportes[-500:]
    with open(REPORTES_PATH, "w", encoding="utf-8") as f:
        json.dump(reportes, f, ensure_ascii=False, indent=2)

# ─── Rutas ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", tiendas=TIENDAS)

@app.route("/api/buscar")
def buscar():
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    if len(q) > 100:
        return jsonify({"error": "Query demasiado larga"}), 400

    productos = get_productos()
    terminos_variantes, sinonimos_set = preparar_query(q)

    directos = []
    sinonimos_res = []

    for p in productos:
        nombre = re.sub(r"[-./ ]", " ", p["nombre"].lower())
        nombre = re.sub(r" +", " ", nombre)
        score = calcular_score(nombre, terminos_variantes)
        if score >= 0:
            directos.append((score, p))
            continue
        if sinonimos_set:
            for sin in sinonimos_set:
                nombre_junto = nombre.replace(" ", "")
                patron = r"(?<![a-z0-9])" + re.escape(sin) + r"(?![a-z0-9])"
                if re.search(patron, nombre) or sin in nombre_junto:
                    sinonimos_res.append((1, p))
                    break

    # Ordenar: con precio primero (asc), sin precio al final
    # Directos antes que sinónimos dentro del mismo rango de precio
    def sort_key_directo(x):
        score, p = x
        tiene_precio = 0 if p["precio"] > 0 else 1
        return (tiene_precio, p["precio"] if p["precio"] > 0 else 999_999_999)

    def sort_key_sinonimo(x):
        _, p = x
        tiene_precio = 0 if p["precio"] > 0 else 1
        return (tiene_precio, p["precio"] if p["precio"] > 0 else 999_999_999)

    directos.sort(key=sort_key_directo)
    sinonimos_res.sort(key=sort_key_sinonimo)

    # Mezclar: con precio de directos, con precio de sinónimos, sin precio
    directos_con = [(s,p) for s,p in directos if p["precio"] > 0]
    directos_sin = [(s,p) for s,p in directos if p["precio"] == 0]
    sin_con = [(s,p) for s,p in sinonimos_res if p["precio"] > 0]
    sin_sin = [(s,p) for s,p in sinonimos_res if p["precio"] == 0]

    combinados = directos_con + sin_con + directos_sin + sin_sin
    return jsonify([p for _, p in combinados[:60]])

@app.route("/api/actualizar", methods=["POST"])
def actualizar():
    def _run():
        nuevos = correr_scraper()
        _cache["productos"] = nuevos
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Actualizando en segundo plano..."})

@app.route("/api/historial/<producto_id>")
def historial_producto(producto_id):
    hist = get_historial()
    datos = hist.get(producto_id, [])
    return jsonify(datos)

@app.route("/api/reporte", methods=["POST"])
def reporte():
    data = request.get_json(silent=True) or {}
    producto_id = str(data.get("id", ""))[:50]
    nombre = str(data.get("nombre", ""))[:200]
    tienda = str(data.get("tienda", ""))[:100]
    precio_actual = float(data.get("precio", 0))
    comentario = str(data.get("comentario", ""))[:200]
    ip = request.remote_addr or ""
    if not producto_id or not nombre:
        return jsonify({"error": "Datos incompletos"}), 400
    guardar_reporte(producto_id, nombre, tienda, precio_actual, comentario, ip)
    return jsonify({"ok": True})

@app.route("/admin/reportes")
def ver_reportes():
    clave = request.args.get("clave", "")
    CLAVE_ADMIN = os.environ.get("ADMIN_CLAVE", "odonto2024")
    if clave != CLAVE_ADMIN:
        return "Acceso denegado", 403
    if not os.path.exists(REPORTES_PATH):
        return "No hay reportes todavia.", 200
    try:
        import csv, io
        reportes = json.load(open(REPORTES_PATH, encoding="utf-8"))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Fecha", "Tienda", "Producto", "Precio actual", "Comentario"])
        for r in reversed(reportes):
            writer.writerow([r.get("fecha",""), r.get("tienda",""), r.get("nombre",""),
                             r.get("precio_actual",""), r.get("comentario","")])
        from flask import Response
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                       headers={"Content-Disposition": "attachment; filename=reportes_odontoprecio.csv"})
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/api/stats")
def stats():
    productos = get_productos()
    por_tienda = {}
    for p in productos:
        t = p["tienda_nombre"]
        por_tienda[t] = por_tienda.get(t, 0) + 1
    return jsonify({"total": len(productos), "por_tienda": por_tienda})

_actualizar_si_es_necesario()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"\n🦷 OdontoPrecio arrancando en puerto {port}...")
    if debug:
        print(f"📡 Abrí tu navegador en: http://localhost:{port}\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
