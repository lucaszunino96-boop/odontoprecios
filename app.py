"""
app.py - Servidor web de OdontoPrecio.
"""

import re, json, os, threading, hashlib
from flask import Flask, render_template, request, jsonify, Response
from rapidfuzz import fuzz
from scraper import cargar_productos, correr_scraper, TIENDAS

app = Flask(__name__)

# ─── Cache ────────────────────────────────────────────────────────────────────
_cache = {"productos": None, "historial": None, "nombres_norm": None}
_file_lock = threading.Lock()  # FIX: lock para escritura de archivos

def get_productos():
    if _cache["productos"] is None:
        _cache["productos"] = cargar_productos()
        _cache["nombres_norm"] = None
    return _cache["productos"]

def get_nombres_norm():
    if _cache["nombres_norm"] is None:
        productos = get_productos()
        _cache["nombres_norm"] = [
            re.sub(r" +", " ", re.sub(r"[-./()\\[\\]]", " ", p["nombre"].lower())).strip()
            for p in productos
        ]
    return _cache["nombres_norm"]

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
            print(f"Datos tienen {edad_dias:.1f} dias — actualizando...")
        else:
            print("No hay datos — scrapeando por primera vez...")
        def _run():
            nuevos = correr_scraper()
            _cache["productos"] = nuevos
            _cache["nombres_norm"] = None
            try:
                hist = guardar_historial(nuevos)
                _cache["historial"] = hist
            except Exception as e:
                print(f"Error guardando historial: {e}")
            print(f"Auto-actualizacion completada: {len(nuevos)} productos.")
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f"Error en auto-actualizacion: {e}")


# ─── BÚSQUEDA ─────────────────────────────────────────────────────────────────
STOPWORDS = {"de","el","la","lo","los","las","en","con","por","para","y","o","e","un","una","x"}
MIN_FUZZY = 75

def normalizar(texto):
    t = re.sub(r"[-./()\\[\\]]", " ", texto.lower())
    return re.sub(r" +", " ", t).strip()

def busqueda_exacta(q_norm, productos, nombres_norm):
    """Todos los tokens del query deben aparecer en el nombre."""
    tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    if not tokens:
        return []
    # FIX: pre-compilar regex una sola vez por búsqueda (2.4x más rápido)
    patrones = [re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])") for t in tokens]
    resultados = []
    for i, nombre in enumerate(nombres_norm):
        nombre_junto = nombre.replace(" ", "")
        if all(p.search(nombre) or tokens[j] in nombre_junto for j, p in enumerate(patrones)):
            resultados.append(productos[i])
    return resultados

def score_fuzzy(q_norm, nombre_norm):
    tokens_q = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 2]
    if not tokens_q:
        return 0
    nombre_junto = nombre_norm.replace(" ", "")
    alguno_presente = any(
        any(tq in tn or tn in tq for tn in nombre_norm.split()) or tq in nombre_junto
        for tq in tokens_q
    )
    if not alguno_presente:
        return 0
    return max(int(fuzz.partial_ratio(q_norm, nombre_norm)),
               int(fuzz.token_set_ratio(q_norm, nombre_norm)))

def busqueda_fuzzy(q_norm, productos, nombres_norm, excluir_ids=None):
    excluir = excluir_ids or set()
    resultados = []
    for i, nombre in enumerate(nombres_norm):
        p = productos[i]
        if p["id"] in excluir:
            continue
        s = score_fuzzy(q_norm, nombre)
        if s >= MIN_FUZZY:
            resultados.append((s, p))
    resultados.sort(key=lambda x: -x[0])
    return [p for _, p in resultados]

def sort_por_precio(productos):
    con = sorted([p for p in productos if p["precio"] > 0], key=lambda p: p["precio"])
    sin = [p for p in productos if p["precio"] == 0]
    return con + sin


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
    with _file_lock:  # FIX: lock para evitar race condition
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
    with _file_lock:  # FIX: lock para evitar race condition
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
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    if len(q) > 100:
        return jsonify({"error": "Query demasiado larga"}), 400

    # FIX: try/catch para offset inválido
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (ValueError, TypeError):
        offset = 0
    limit = 30

    q_norm = normalizar(q)
    productos = get_productos()
    nombres_norm = get_nombres_norm()

    exactos = busqueda_exacta(q_norm, productos, nombres_norm)

    fuzzy = []
    if len(exactos) < 10:
        ids_exactos = {p["id"] for p in exactos}
        fuzzy = busqueda_fuzzy(q_norm, productos, nombres_norm, excluir_ids=ids_exactos)

    todos = sort_por_precio(exactos + fuzzy)
    total = len(todos)
    return jsonify({"resultados": todos[offset:offset+limit], "total": total, "offset": offset, "limit": limit})

@app.route("/api/actualizar", methods=["POST"])
def actualizar():
    # FIX: requiere clave para evitar DoS
    clave = request.args.get("clave", "")
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE:
        return jsonify({"error": "No autorizado"}), 403
    def _run():
        nuevos = correr_scraper()
        _cache["productos"] = nuevos
        _cache["nombres_norm"] = None
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Actualizando en segundo plano..."})

@app.route("/api/historial/<producto_id>")
def historial_producto(producto_id):
    hist = get_historial()
    return jsonify(hist.get(producto_id, []))

@app.route("/api/reporte", methods=["POST"])
def reporte():
    data = request.get_json(silent=True) or {}
    producto_id = str(data.get("id", ""))[:50]
    nombre = str(data.get("nombre", ""))[:200]
    tienda = str(data.get("tienda", ""))[:100]
    # FIX: try/catch para precio inválido
    try:
        precio_actual = float(data.get("precio", 0))
    except (ValueError, TypeError):
        precio_actual = 0.0
    comentario = str(data.get("comentario", ""))[:200]
    ip = request.remote_addr or ""
    if not producto_id or not nombre:
        return jsonify({"error": "Datos incompletos"}), 400
    guardar_reporte(producto_id, nombre, tienda, precio_actual, comentario, ip)
    return jsonify({"ok": True})

@app.route("/admin/reportes")
def ver_reportes():
    clave = request.args.get("clave", "")
    # FIX: sin fallback débil — si no hay var de entorno, siempre bloquear
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE:
        return "Acceso denegado", 403
    if not os.path.exists(REPORTES_PATH):
        return "No hay reportes todavia.", 200
    try:
        import csv, io
        with open(REPORTES_PATH, encoding="utf-8") as f:  # FIX: context manager
            reportes = json.load(f)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Fecha", "Tienda", "Producto", "Precio actual", "Comentario"])
        for r in reversed(reportes):
            writer.writerow([r.get("fecha",""), r.get("tienda",""), r.get("nombre",""),
                             r.get("precio_actual",""), r.get("comentario","")])
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                       headers={"Content-Disposition": "attachment; filename=reportes.csv"})
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
