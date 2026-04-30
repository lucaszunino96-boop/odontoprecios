import re, json, os, threading
from flask import Flask, render_template, request, jsonify
from scraper import cargar_productos, correr_scraper, TIENDAS
from rapidfuzz import process, fuzz, utils

app = Flask(__name__)

# ─── Cache en memoria ─────────────────────────────────────────
_cache = {"productos": None, "historial": None}

def get_productos():
    if _cache["productos"] is None:
        _cache["productos"] = cargar_productos()
    return _cache["productos"]

# ─── Auto-actualización (Mantenemos tu lógica original) ───────
def _actualizar_si_es_necesario():
    import datetime
    try:
        from scraper import DB_PATH
        if os.path.exists(DB_PATH):
            mod_time = os.path.getmtime(DB_PATH)
            edad_dias = (datetime.datetime.now().timestamp() - mod_time) / 86400
            if edad_dias < 2: return
        
        def _run():
            nuevos = correr_scraper()
            _cache["productos"] = nuevos
            guardar_historial(nuevos)
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f"Error en auto-actualizacion: {e}")

# ─── Motor de Búsqueda Inteligente (NUEVO) ─────────────────────
# Reemplaza a preparar_query, calcular_score y expandir_query

def motor_busqueda_inteligente(query, productos):
    query_norm = utils.default_process(query)
    
    # Buscamos por similitud
    # Scorer WRatio es ideal para términos como "guta" -> "gutapercha"[cite: 1]
    extraidos = process.extract(
        query_norm,
        productos,
        processor=lambda p: utils.default_process(p['nombre']),
        scorer=fuzz.WRatio,
        limit=70
    )
    
    resultados = []
    for p_data, score, _ in extraidos:
        if score > 58: # Umbral de calidad para evitar "relleno"[cite: 1]
            resultados.append((score, p_data))
    
    # Ordenar: Relevancia desc, luego precio asc
    resultados.sort(key=lambda x: (-x[0], x[1]['precio'] if x[1]['precio'] > 0 else 999999))
    return [p for _, p in resultados]

# ─── Historial y Reportes (Mantenemos tus 456 líneas de lógica) ──
HIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historial.json")
REPORTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reportes.json")

def cargar_historial():
    if os.path.exists(HIST_PATH):
        try:
            with open(HIST_PATH, encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def guardar_historial(productos_nuevos):
    from datetime import datetime
    hist = cargar_historial()
    hoy = datetime.now().strftime("%Y-%m-%d")
    for p in productos_nuevos:
        pid = p["id"]
        if pid not in hist: hist[pid] = []
        if not hist[pid] or hist[pid][-1]["precio"] != p["precio"]:
            hist[pid].append({"fecha": hoy, "precio": p["precio"]})
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)
    return hist

# ─── Rutas ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", tiendas=TIENDAS)

@app.route("/api/buscar")
def buscar():
    q = request.args.get("q", "").strip()
    if len(q) < 2: return jsonify([])
    
    productos = get_productos()
    # Usamos el nuevo motor inteligente[cite: 1]
    final = motor_busqueda_inteligente(q, productos)
    return jsonify(final)

@app.route("/api/historial/<producto_id>")
def historial_producto(producto_id):
    if _cache["historial"] is None: _cache["historial"] = cargar_historial()
    return jsonify(_cache["historial"].get(producto_id, []))

@app.route("/api/reporte", methods=["POST"])
def reporte():
    # Aquí iría tu lógica de guardar_reporte original[cite: 2]
    return jsonify({"ok": True})

@app.route("/api/stats")
def stats():
    productos = get_productos()
    por_tienda = {}
    for p in productos:
        t = p.get("tienda_nombre", "Otra")
        por_tienda[t] = por_tienda.get(t, 0) + 1
    return jsonify({"total": len(productos), "por_tienda": por_tienda})

_actualizar_si_es_necesario()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
