"""
app.py - OdontoPrecio

Arquitectura de datos:
- productos.json se descarga desde GitHub Raw al iniciar
- Se verifica cada 15 minutos si cambió (por ETag/hash)
- Si falla GitHub, usa la última copia válida en disco
- Sin dependencia del filesystem efímero de Render
"""

import re, json, os, threading, hashlib, time, urllib.request
from flask import Flask, render_template, request, jsonify, Response
from rapidfuzz import fuzz
from scraper import cargar_productos, correr_scraper, TIENDAS
from catalogador import catalogar, clasificar_tokens, _TOKENS_GENERICOS

app = Flask(__name__)

# ─── CONFIGURACIÓN GITHUB RAW ─────────────────────────────────────────────────
GITHUB_RAW_URL = os.environ.get(
    "PRODUCTOS_JSON_URL",
    "https://raw.githubusercontent.com/lucaszunino96-boop/odontoprecios/main/productos.json"
)
CACHE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "productos_cache.json")
REFRESH_INTERVAL = 15 * 60  # 15 minutos

# ─── ESTADO ──────────────────────────────────────────────────────────────────
_estado = {
    "productos": None,
    "nombres_norm": None,
    "historial": None,
    "ultima_carga": None,       # datetime de la última carga exitosa
    "origen": None,             # "github" | "cache_local" | "disco"
    "hash_actual": None,        # hash de productos del scraper
    "fecha_run": None,          # fecha_run del scraper (del campo meta)
    "total": 0,
    "error_ultimo": None,
    "refresh_en_curso": False,
}
_data_lock = threading.Lock()
_file_lock = threading.Lock()


# ─── CARGA DE PRODUCTOS DESDE GITHUB ─────────────────────────────────────────

def _descargar_json_github():
    """Descarga productos.json desde GitHub Raw. Retorna (bytes, etag) o lanza excepción."""
    req = urllib.request.Request(
        GITHUB_RAW_URL,
        headers={"User-Agent": "OdontoPrecio/1.0", "Cache-Control": "no-cache"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        etag = resp.headers.get("ETag", "")
        return data, etag

def _hash_datos(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:16]

def _cargar_desde_bytes(data: bytes) -> tuple:
    """
    Soporta dos formatos:
    - Nuevo: {"productos": [...], "meta": {...}}
    - Viejo: [...] (compatibilidad)
    Retorna (lista_productos, meta_dict)
    """
    parsed = json.loads(data)
    if isinstance(parsed, dict) and "productos" in parsed:
        productos = parsed["productos"]
        meta = parsed.get("meta", {})
    else:
        productos = parsed  # formato viejo: lista directa
        meta = {}
    filtrados = [
        p for p in productos
        if len(p.get("nombre", "").strip()) >= 8
        and p.get("precio", 0) > 0
    ]
    return filtrados, meta

def cargar_productos_inicial():
    """
    Carga productos al iniciar la app.
    Orden de prioridad:
    1. GitHub Raw (fresco)
    2. Cache local productos_cache.json (si GitHub falla)
    3. productos.json del disco (fallback final)
    """
    from datetime import datetime

    # Intento 1: GitHub Raw
    try:
        print("  Descargando productos.json desde GitHub Raw...")
        data, etag = _descargar_json_github()
        productos, meta = _cargar_desde_bytes(data)
        h = meta.get("hash_productos") or _hash_datos(data)
        fecha_run = meta.get("fecha_run", "")

        # Guardar cache local
        with open(CACHE_LOCAL, "wb") as f:
            f.write(data)

        with _data_lock:
            _estado["productos"] = productos
            _estado["nombres_norm"] = None
            _estado["ultima_carga"] = datetime.now()
            _estado["origen"] = "github"
            _estado["hash_actual"] = h
            _estado["total"] = len(productos)
            _estado["error_ultimo"] = None
            _estado["fecha_run"] = fecha_run

        print(f"  ✅ GitHub Raw: {len(productos)} productos (hash: {h}, run: {fecha_run})")
        construir_indice(productos)
        return

    except Exception as e:
        print(f"  ⚠ GitHub Raw falló: {e}")
        _estado["error_ultimo"] = str(e)

    # Intento 2: Cache local
    if os.path.exists(CACHE_LOCAL):
        try:
            print("  Usando cache local productos_cache.json...")
            with open(CACHE_LOCAL, "rb") as f:
                data = f.read()
            productos, meta = _cargar_desde_bytes(data)
            h = meta.get("hash_productos") or _hash_datos(data)
            fecha_run = meta.get("fecha_run", "")

            with _data_lock:
                _estado["productos"] = productos
                _estado["nombres_norm"] = None
                _estado["ultima_carga"] = datetime.now()
                _estado["origen"] = "cache_local"
                _estado["hash_actual"] = h
                _estado["total"] = len(productos)
                _estado["fecha_run"] = fecha_run

            print(f"  ✅ Cache local: {len(productos)} productos")
            construir_indice(productos)
            return
        except Exception as e:
            print(f"  ⚠ Cache local falló: {e}")

    # Intento 3: Disco (productos.json del deploy)
    try:
        print("  Usando productos.json del disco...")
        productos_disco = cargar_productos()
        # cargar_productos() ya devuelve lista (maneja formato nuevo y viejo)
        if isinstance(productos_disco, dict) and "productos" in productos_disco:
            productos_disco = productos_disco["productos"]
        elif not isinstance(productos_disco, list):
            productos_disco = []
        productos = [
            p for p in productos_disco
            if isinstance(p, dict)
            and len(p.get("nombre", "").strip()) >= 8
            and p.get("precio", 0) > 0
        ]
        with _data_lock:
            _estado["productos"] = productos
            _estado["nombres_norm"] = None
            _estado["ultima_carga"] = datetime.now()
            _estado["origen"] = "disco"
            _estado["total"] = len(productos)

        print(f"  ✅ Disco: {len(productos)} productos")
        construir_indice(productos)
    except Exception as e:
        print(f"  ❌ Disco también falló: {e}")


def verificar_actualizacion():
    """
    Corre en background cada 15 minutos.
    Compara el hash del JSON en GitHub con el actual.
    Si cambió, recarga.
    """
    from datetime import datetime

    while True:
        time.sleep(REFRESH_INTERVAL)
        if _estado["refresh_en_curso"]:
            continue

        try:
            _estado["refresh_en_curso"] = True
            print(f"[{datetime.now().strftime('%H:%M')}] Verificando actualizaciones...")

            data, _ = _descargar_json_github()
            productos, meta = _cargar_desde_bytes(data)
            h = meta.get("hash_productos") or _hash_datos(data)

            if h == _estado.get("hash_actual"):
                print(f"  Sin cambios (hash: {h})")
                continue

            fecha_run = meta.get("fecha_run", "")
            print(f"  Hash cambió {_estado.get('hash_actual')} → {h}, recargando (run: {fecha_run})...")

            # Guardar cache
            with open(CACHE_LOCAL, "wb") as f:
                f.write(data)

            # Actualizar estado
            with _data_lock:
                _estado["productos"] = productos
                _estado["nombres_norm"] = None
                _estado["ultima_carga"] = datetime.now()
                _estado["origen"] = "github"
                _estado["hash_actual"] = h
                _estado["total"] = len(productos)
                _estado["error_ultimo"] = None
                _estado["fecha_run"] = fecha_run

            # Reconstruir índice
            construir_indice(productos)
            print(f"  ✅ Recargado: {len(productos)} productos")

        except Exception as e:
            print(f"  ⚠ Error en verificación: {e}")
            _estado["error_ultimo"] = str(e)
        finally:
            _estado["refresh_en_curso"] = False


def get_productos():
    if _estado["productos"] is None:
        cargar_productos_inicial()
    return _estado["productos"] or []

def get_nombres_norm():
    return get_nombres_norm_con_indice()


# ─── BÚSQUEDA ─────────────────────────────────────────────────────────────────
import unicodedata
from collections import defaultdict

STOPWORDS = {"de","el","la","lo","los","las","en","con","por","para","y","o","e","un","una","x","a"}
MIN_FUZZY = 72

def normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[-./()%,;:!?\\[\\]]", " ", t)
    return re.sub(r" +", " ", t).strip()

def stemming_basico(token):
    if len(token) <= 3: return token
    if token.endswith("ces"):  return token[:-3] + "z"
    if token.endswith("ques"): return token[:-3] + "ca"
    if token.endswith("es") and len(token) > 4: return token[:-2]
    if token.endswith("s") and len(token) > 3:  return token[:-1]
    return token

# Marcas — filtro duro
_MARCAS = {
    '3m','ivoclar','dentsply','angelus','gc','kavo','sirona','voco',
    'kerr','ultradent','ormco','medibase','septodont','zhermack','bego',
    'woodpecker','nsk','morita','hu-friedy','solventum','espe',
    'american orthodontics','coltene','shofu','tokuyama','bisco',
    'anescart','alphacaine','mepinor','scandicaine','ultracaine',
    'klepp','metabiomed','maillefer','sdi','coltene','brilliant',
    'filtek','protaper','waveone','fuji','tetric','opalescence',
}

# ─── ÍNDICE INVERTIDO ─────────────────────────────────────────────────────────
_indice: dict = {}
_nombres_norm_cache: list = []

def construir_indice(productos):
    global _indice, _nombres_norm_cache
    from catalogador import SINONIMOS_GRUPOS, _norm_sin
    indice = defaultdict(set)
    nombres_norm = []

    # Mapa de sinónimos
    sin_map = {}
    for grupo in SINONIMOS_GRUPOS:
        for termino in grupo:
            tn = _norm_sin(termino)
            sin_map[tn] = {_norm_sin(s) for s in grupo if s != termino}

    for i, p in enumerate(productos):
        norm = normalizar(p["nombre"])
        nombres_norm.append(norm)
        tokens = [t for t in norm.split() if t not in STOPWORDS and len(t) > 1]
        for token in tokens:
            stem = stemming_basico(token)
            indice[token].add(i)
            if stem != token: indice[stem].add(i)
            for s in sin_map.get(token, set()):
                indice[f"__sin__{s}"].add(i)

    with _data_lock:
        _indice = dict(indice)
        _nombres_norm_cache = nombres_norm

    print(f"  Índice construido: {len(_indice)} tokens, {len(productos)} productos")
    return nombres_norm

def get_nombres_norm_con_indice():
    productos = get_productos()
    if not _nombres_norm_cache or len(_nombres_norm_cache) != len(productos):
        return construir_indice(productos)
    return _nombres_norm_cache

def busqueda_por_indice(tokens_query):
    if not tokens_query or not _indice: return None
    sets_por_token = []
    for token in tokens_query:
        stem = stemming_basico(token)
        candidatos = set()
        if token in _indice: candidatos |= _indice[token]
        if stem in _indice: candidatos |= _indice[stem]
        if len(token) >= 3:
            for key in _indice:
                if key.startswith(token) and not key.startswith("__sin__"):
                    candidatos |= _indice[key]
        sin_key = f"__sin__{token}"
        if sin_key in _indice: candidatos |= _indice[sin_key]
        if not candidatos: return set()
        sets_por_token.append(candidatos)
    resultado = sets_por_token[0]
    for s in sets_por_token[1:]:
        resultado = resultado & s
    return resultado

# Motor de relevancia
import re as _re

_STOP_LOCAL = {"de","el","la","los","las","en","con","por","para","y","o","e","un","una","x","a",
               "composite","resina","adhesivo","cemento","guante","guantes","lima","fresa",
               "bracket","disco","anestesia","cemento","yeso","cono","conos","aguja","agujas"}

def _token_presente_en(tok, nombre_norm, nombre_junto):
    tok_clean = _re.sub(r'^[^a-z0-9]+', '', tok)
    if not tok_clean: return False
    if len(tok_clean) <= 3:
        return bool(_re.search(r'\b' + _re.escape(tok_clean) + r'\b', nombre_norm))
    return (tok_clean in nombre_norm or tok_clean in nombre_junto or
            any(nt.startswith(tok_clean) or tok_clean.startswith(_re.sub(r'[a-z]+$','',nt))
                for nt in nombre_norm.split() if len(nt) >= 2))


def _get_attrs(producto: dict) -> dict:
    """
    Usa attrs pre-calculados si existen y son confiables.
    Recataloga en tiempo real si el producto es una copia/símil
    (los attrs viejos pueden tener marca incorrecta para estos casos).
    """
    nombre = producto.get("nombre", "")
    # Si el nombre indica que es una copia, recatalogar siempre
    import re as _re2
    _nombre_norm = nombre.lower()
    import unicodedata as _ud
    _nombre_norm = "".join(c for c in _ud.normalize("NFD", _nombre_norm) if _ud.category(c) != "Mn")
    if _re2.search(r"\b(simil|similar|tipo|alternativ|generico)\b", _nombre_norm):
        return catalogar(nombre)
    attrs = producto.get("attrs")
    if attrs and isinstance(attrs, dict) and len(attrs) > 0:
        return attrs
    return catalogar(nombre)

def score_relevancia(q_tokens, q_attrs, nombre_norm, prod_attrs):
    score = 0
    nombre_junto = nombre_norm.replace(" ","")
    n_esp = len(q_tokens["especificos"])
    presentes, ausentes = [], []

    for tok in q_tokens["especificos"]:
        if _token_presente_en(tok, nombre_norm, nombre_junto):
            presentes.append(tok); score += 120
        else:
            ausentes.append(tok); score -= 80

    if n_esp > 0 and not presentes: return -200

    if n_esp >= 2 and ausentes:
        frac = len(ausentes) / n_esp
        modelo_ausente = any(_re.search(r'[a-z]+[0-9]{2,}', t) for t in ausentes)
        score -= int(frac * (180 if modelo_ausente else 120))

    for tok in q_tokens["genericos"]:
        if tok in nombre_norm or tok in nombre_junto: score += 20

    q_all = " ".join(q_tokens["todos"])
    if fuzz.partial_ratio(q_all, nombre_norm) >= 88: score += 80

    for attr in ["tono","material","calibre","droga","talle"]:
        qv, pv = q_attrs.get(attr), prod_attrs.get(attr)
        if qv and pv:
            qs, ps = str(qv).lower().replace("-",""), str(pv).lower().replace("-","")
            if qs != ps and not qs.startswith(ps) and not ps.startswith(qs):
                score -= 150

    qm, pm = q_attrs.get("modelo"), prod_attrs.get("modelo")
    if qm and pm:
        pq = _re.sub(r'[a-z]+$','',qm); pp = _re.sub(r'[a-z]+$','',pm)
        if not (pm==qm or pm.startswith(pq) or qm.startswith(pp)):
            score -= 200

    return max(-200, min(300, score))

def score_fuzzy_typo(q_norm, nombre_norm):
    return max(int(fuzz.token_set_ratio(q_norm, nombre_norm)),
               int(fuzz.partial_ratio(q_norm, nombre_norm)))

def busqueda_fuzzy(q_norm, productos, nombres_norm, excluir_ids=None):
    excluir = excluir_ids or set()
    q_tokens = clasificar_tokens(q_norm)
    q_attrs = catalogar(q_norm)
    tiene_esp = bool(q_tokens["especificos"])
    resultados = []
    for i, nombre in enumerate(nombres_norm):
        p = productos[i]
        if p["id"] in excluir: continue
        if tiene_esp:
            p_attrs = _get_attrs(p)
            s = score_relevancia(q_tokens, q_attrs, nombre, p_attrs)
            if s >= -50: resultados.append((s, p))
        else:
            s = score_fuzzy_typo(q_norm, nombre)
            if s >= MIN_FUZZY: resultados.append((s, p))
    resultados.sort(key=lambda x: -x[0])
    return [p for _, p in resultados]

def sort_por_precio(productos):
    con = sorted([p for p in productos if p["precio"] > 0], key=lambda p: p["precio"])
    return con + [p for p in productos if p["precio"] == 0]


# ─── Historial ────────────────────────────────────────────────────────────────
HIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historial.json")

def cargar_historial():
    if os.path.exists(HIST_PATH):
        try:
            with open(HIST_PATH, encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def guardar_historial(productos_nuevos):
    from datetime import datetime
    with _file_lock:
        hist = cargar_historial()
        hoy = datetime.now().strftime("%Y-%m-%d")
        for p in productos_nuevos:
            pid, precio = p["id"], p["precio"]
            if pid not in hist: hist[pid] = []
            if not hist[pid] or hist[pid][-1]["precio"] != precio:
                hist[pid].append({"fecha": hoy, "precio": precio})
                if len(hist[pid]) > 90: hist[pid] = hist[pid][-90:]
        with open(HIST_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
        return hist

_estado["historial"] = None

def get_historial():
    if _estado["historial"] is None:
        _estado["historial"] = cargar_historial()
    return _estado["historial"]


# ─── Reportes ─────────────────────────────────────────────────────────────────
REPORTES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reportes.json")

def guardar_reporte(producto_id, nombre, tienda, precio_actual, comentario, ip):
    from datetime import datetime
    with _file_lock:
        reportes = []
        if os.path.exists(REPORTES_PATH):
            try:
                with open(REPORTES_PATH, encoding="utf-8") as f: reportes = json.load(f)
            except: reportes = []
        reportes.append({
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "producto_id": producto_id, "nombre": nombre, "tienda": tienda,
            "precio_actual": precio_actual, "comentario": comentario[:200],
            "ip": ip[:20] if ip else ""
        })
        reportes = reportes[-500:]
        with open(REPORTES_PATH, "w", encoding="utf-8") as f:
            json.dump(reportes, f, ensure_ascii=False, indent=2)


# ─── RUTAS ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", tiendas=TIENDAS)

@app.route("/api/buscar")
def buscar():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"resultados":[],"total":0,"offset":0,"limit":30,"aviso":None,"sugerencia":None})
    if len(q) > 100:
        return jsonify({"error": "Query demasiado larga"}), 400
    try: offset = max(0, int(request.args.get("offset", 0)))
    except: offset = 0
    limit = 30

    q_norm = normalizar(q)
    productos = get_productos()
    nombres_norm = get_nombres_norm()

    q_tokens = clasificar_tokens(q_norm)
    q_attrs = catalogar(q_norm)
    tiene_especificos = bool(q_tokens["especificos"])

    # Candidatos por índice
    tokens_idx = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    candidatos_idx = busqueda_por_indice(tokens_idx)
    candidatos = list(candidatos_idx) if candidatos_idx is not None else list(range(len(productos)))

    # Filtro duro de marca
    # Si el query no tiene marca explícita, inferirla del modelo (p60→3m, protaper→dentsply, etc.)
    marcas_q = [t for t in tokens_idx if t in _MARCAS]
    if not marcas_q and q_attrs.get("marca"):
        marcas_q = [q_attrs["marca"]]
    if marcas_q:
        def _tiene_marca(i):
            nombre = nombres_norm[i]
            # Buscar en el nombre
            if any(m in nombre or m in nombre.replace(" ","") for m in marcas_q):
                return True
            # Buscar en attrs pre-calculados
            p_attrs = productos[i].get("attrs") or {}
            p_marca = p_attrs.get("marca","")
            if any(m == p_marca for m in marcas_q):
                return True
            return False
        con_marca = [i for i in candidatos if _tiene_marca(i)]
        if con_marca: candidatos = con_marca

    # Filtro duro de modelo
    modelo_q = q_attrs.get("modelo")
    if modelo_q and len(modelo_q) >= 3:
        pq = _re.sub(r'[a-z]+$','', modelo_q)
        def _modelo_ok(i):
            pa = _get_attrs(productos[i])
            mp = pa.get("modelo"); pn = nombres_norm[i]
            if mp is None: return modelo_q in pn or _re.sub(r'^[a-z]+','',modelo_q) in pn
            pp2 = _re.sub(r'[a-z]+$','',mp)
            return mp==modelo_q or mp.startswith(pq) or modelo_q.startswith(pp2)
        cm = [i for i in candidatos if _modelo_ok(i)]
        if cm: candidatos = cm

    # Scoring
    if tiene_especificos:
        scored = []
        for i in candidatos:
            p_attrs = _get_attrs(productos[i])
            s = score_relevancia(q_tokens, q_attrs, nombres_norm[i], p_attrs)
            scored.append((s, productos[i]))
        scored.sort(key=lambda x: (-x[0], x[1]["precio"]))
        todos = [p for s,p in scored if s > -100]
        if len(todos) < 5: todos = [p for s,p in scored if s > -200]
    else:
        todos = sort_por_precio([productos[i] for i in candidatos])

    if not todos: todos = busqueda_fuzzy(q_norm, productos, nombres_norm)

    total = len(todos)
    aviso = None
    if not tiene_especificos and total > 200:
        aviso = "Agregá marca, modelo o medida para resultados más precisos"
    sugerencia = None
    if not todos:
        fb = busqueda_fuzzy(q_norm, productos, nombres_norm)
        if fb: sugerencia = f"¿Buscabas: {fb[0]['nombre'][:50]}?"

    return jsonify({"resultados": todos[offset:offset+limit], "total": total,
                    "offset": offset, "limit": limit, "aviso": aviso, "sugerencia": sugerencia})

@app.route("/api/autocomplete")
def autocomplete():
    q = request.args.get("q","").strip()
    if len(q) < 2: return jsonify([])
    q_norm = normalizar(q)
    tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    if not tokens: return jsonify([])
    productos = get_productos()
    nombres_norm = get_nombres_norm()
    candidatos_idx = busqueda_por_indice(tokens)
    if candidatos_idx is None: return jsonify([])
    vistos, sugerencias = set(), []
    for i in sorted(candidatos_idx):
        p = productos[i]
        k = p["nombre"].lower()[:40]
        if k in vistos: continue
        vistos.add(k)
        sugerencias.append({"nombre":p["nombre"],"tienda":p["tienda_nombre"],"precio_fmt":p["precio_fmt"]})
        if len(sugerencias) >= 6: break
    return jsonify(sugerencias)

@app.route("/api/estado")
def estado():
    from datetime import datetime
    ultima_fmt = "No disponible"
    if _estado["ultima_carga"]:
        hoy = datetime.now().date()
        dt = _estado["ultima_carga"]
        ultima_fmt = f"hoy {dt.strftime('%H:%M')}" if dt.date() == hoy else dt.strftime("%d/%m %H:%M")

    return jsonify({
        "total_productos": _estado["total"],
        "tiendas_totales": len(TIENDAS),
        "tiendas_ok": len(TIENDAS),
        "tiendas_error": 0,
        "ultima_actualizacion": _estado["ultima_carga"].isoformat() if _estado["ultima_carga"] else None,
        "ultima_fmt": ultima_fmt,
        "origen_datos": _estado["origen"],
        "hash_actual": _estado["hash_actual"],
        "fecha_run_scraper": _estado.get("fecha_run"),
        "error_ultimo": _estado["error_ultimo"],
        "texto_header": f"{_estado['total']:,} productos · {len(TIENDAS)} tiendas · actualizado {ultima_fmt}".replace(",","."),
    })

@app.route("/api/historial/<producto_id>")
def historial_producto(producto_id):
    hist = get_historial()
    entradas = hist.get(producto_id, [])
    variacion = None; precio_30d = None
    if len(entradas) >= 2:
        from datetime import datetime, timedelta
        actual = entradas[-1]["precio"]
        hace_30 = datetime.now() - timedelta(days=30)
        for e in reversed(entradas[:-1]):
            try:
                if datetime.strptime(e["fecha"],"%Y-%m-%d") <= hace_30 + timedelta(days=5):
                    precio_30d = e["precio"]
                    if precio_30d > 0: variacion = round(((actual-precio_30d)/precio_30d)*100,1)
                    break
            except: pass
    return jsonify({"entradas":entradas,"precio_30d":precio_30d,"variacion_pct":variacion})

@app.route("/api/reporte", methods=["POST"])
def reporte():
    data = request.get_json(silent=True) or {}
    producto_id = str(data.get("id",""))[:50]
    nombre = str(data.get("nombre",""))[:200]
    tienda = str(data.get("tienda",""))[:100]
    try: precio_actual = float(data.get("precio",0))
    except: precio_actual = 0.0
    comentario = str(data.get("comentario",""))[:200]
    if not producto_id or not nombre: return jsonify({"error":"Datos incompletos"}),400
    guardar_reporte(producto_id, nombre, tienda, precio_actual, comentario, request.remote_addr or "")
    return jsonify({"ok":True})

@app.route("/api/reporte-scraping")
def reporte_scraping():
    rp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reporte_scraping.json")
    if not os.path.exists(rp): return jsonify({"error":"No hay reporte disponible aún."}),404
    with open(rp, encoding="utf-8") as f: return jsonify(json.load(f))

@app.route("/api/stats")
def stats():
    productos = get_productos()
    por_tienda = {}
    for p in productos:
        t = p["tienda_nombre"]; por_tienda[t] = por_tienda.get(t,0)+1
    return jsonify({"total":len(productos),"por_tienda":por_tienda})

@app.route("/api/actualizar", methods=["POST"])
def actualizar():
    clave = request.args.get("clave","")
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE:
        return jsonify({"error":"No autorizado"}),403
    def _run():
        nuevos = correr_scraper()
        with _data_lock:
            _estado["productos"] = [p for p in nuevos if len(p.get("nombre","").strip())>=8 and p.get("precio",0)>0]
            _estado["nombres_norm"] = None
        construir_indice(_estado["productos"])
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok":True,"mensaje":"Actualizando en segundo plano..."})

@app.route("/admin/reportes")
def ver_reportes():
    clave = request.args.get("clave","")
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE: return "Acceso denegado",403
    if not os.path.exists(REPORTES_PATH): return "No hay reportes.",200
    try:
        import csv, io
        with open(REPORTES_PATH, encoding="utf-8") as f: reportes = json.load(f)
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow(["Fecha","Tienda","Producto","Precio","Comentario"])
        for r in reversed(reportes):
            w.writerow([r.get("fecha",""),r.get("tienda",""),r.get("nombre",""),r.get("precio_actual",""),r.get("comentario","")])
        return Response("\ufeff"+output.getvalue(), mimetype="text/csv",
                       headers={"Content-Disposition":"attachment; filename=reportes.csv"})
    except Exception as e: return f"Error: {e}",500

@app.route("/api/compra-inteligente", methods=["POST"])
def compra_inteligente():
    data = request.get_json(silent=True) or {}
    lineas_raw = str(data.get("lista","")).strip().split("\n")
    lineas = [l.strip() for l in lineas_raw if l.strip() and len(l.strip())>1][:30]
    if not lineas: return jsonify({"error":"Lista vacía"}),400

    productos = get_productos()
    nombres_norm = get_nombres_norm()

    def buscar_linea(linea):
        q_norm = normalizar(linea)
        tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t)>1]
        if not tokens:
            return {"linea":linea,"matches":[],"generica":True,"aviso":"Línea muy genérica"}

        es_generica = len(tokens)==1 and len(tokens[0])<=5
        q_attrs = catalogar(linea)
        q_tokens = clasificar_tokens(q_norm)

        # OR de tokens
        tokens_ord = sorted(tokens, key=lambda t: (-len(t), 0 if _re.search(r'[0-9]',t) else 1))
        cands = set()
        for t in tokens_ord:
            stem = stemming_basico(t)
            if t in _indice: cands |= _indice[t]
            if stem in _indice: cands |= _indice[stem]
            for key in _indice:
                if key.startswith(t) and not key.startswith("__sin__"): cands |= _indice[key]

        # Filtro marca
        marcas_q = [t for t in tokens if t in _MARCAS]
        if marcas_q:
            idx_m = set()
            for m in marcas_q:
                if m in _indice: idx_m |= _indice[m]
                for key in _indice:
                    if key.startswith(m) and not key.startswith("__sin__"): idx_m |= _indice[key]
            if idx_m: cands = cands & idx_m if cands else idx_m

        # Filtro modelo
        modelo_q = q_attrs.get("modelo")
        if modelo_q and len(modelo_q)>=3 and cands:
            pq2 = _re.sub(r'[a-z]+$','',modelo_q)
            def _mok(i):
                pa = _get_attrs(productos[i]); mp = pa.get("modelo"); pn = nombres_norm[i]
                if mp is None: return modelo_q in pn or _re.sub(r'^[a-z]+','',modelo_q) in pn
                pp3 = _re.sub(r'[a-z]+$','',mp)
                return mp==modelo_q or mp.startswith(pq2) or modelo_q.startswith(pp3)
            cm = {i for i in cands if _mok(i)}
            if cm: cands = cm

        if not cands:
            for i, nombre in enumerate(nombres_norm):
                s = max(int(fuzz.partial_ratio(q_norm,nombre)), int(fuzz.token_set_ratio(q_norm,nombre)))
                if s >= 50: cands.add(i)

        scored = []
        for i in cands:
            p = productos[i]; p_norm = nombres_norm[i]
            p_attrs = _get_attrs(p)
            base = max(int(fuzz.token_set_ratio(q_norm,p_norm)), int(fuzz.partial_ratio(q_norm,p_norm)))
            q_t_imp = [t for t in q_norm.split() if len(t)>=3 and t not in _STOP_LOCAL and not _re.match(r'^\d+$',t)]
            p_junto = p_norm.replace(" ","")
            ausentes = sum(1 for t in q_t_imp if t not in p_norm and t not in p_junto)
            base_adj = max(0, base - ausentes*8)
            s = score_relevancia(q_tokens, q_attrs, p_norm, p_attrs)
            final = max(0, min(100, (base_adj + max(0,s)) // 2))
            if base >= 45 and final >= 20: scored.append((final, base, p))

        scored.sort(key=lambda x: (-x[0], x[2]["precio"]))
        matches = []
        for sc, base, p in scored[:5]:
            nivel = "alta" if sc>=80 else "media" if sc>=55 else "baja"
            nota = None
            q_tono = q_attrs.get("tono")
            if q_tono and not _get_attrs(p).get("tono"):
                nota = f"Verificar tono {q_tono.upper()} en tienda"
            matches.append({"id":p["id"],"nombre":p["nombre"],"tienda":p["tienda_nombre"],
                            "tienda_slug":p["tienda_slug"],"precio":p["precio"],
                            "precio_fmt":p["precio_fmt"],"url":p.get("url",""),
                            "confianza":sc,"confianza_nivel":nivel,"nota_variante":nota})

        aviso = "Agregá marca o detalle para mejores resultados" if es_generica else None
        return {"linea":linea,"matches":matches,"generica":es_generica,"aviso":aviso}

    resultados = [buscar_linea(l) for l in lineas]

    def calc_est(resultados, tipo):
        from collections import Counter
        items = []
        if tipo == "mas_barato":
            for r in resultados:
                m = min((x for x in r["matches"] if x["precio"]>0),key=lambda x:x["precio"],default=None)
                items.append(m)
        elif tipo == "menos_tiendas":
            cnt = Counter(m["tienda"] for r in resultados for m in r["matches"][:3] if m["precio"]>0)
            top = cnt.most_common(1)[0][0] if cnt else None
            for r in resultados:
                de_top = [x for x in r["matches"] if x["tienda"]==top and x["precio"]>0]
                m = min(de_top,key=lambda x:x["precio"],default=None) or min((x for x in r["matches"] if x["precio"]>0),key=lambda x:x["precio"],default=None)
                items.append(m)
        else:
            cnt = Counter(m["tienda"] for r in resultados for m in r["matches"][:3] if m["precio"]>0)
            top2 = {t for t,_ in cnt.most_common(2)}
            for r in resultados:
                de_top2 = [x for x in r["matches"] if x["tienda"] in top2 and x["precio"]>0]
                m = min(de_top2,key=lambda x:x["precio"],default=None) or min((x for x in r["matches"] if x["precio"]>0),key=lambda x:x["precio"],default=None)
                items.append(m)
        total = sum(x["precio"] for x in items if x)
        tiendas = list({x["tienda"] for x in items if x})
        return {"items":items,"total":total,"n_tiendas":len(tiendas),"tiendas":tiendas}

    return jsonify({
        "lineas": resultados,
        "estrategias": {
            "mas_barato": calc_est(resultados,"mas_barato"),
            "menos_tiendas": calc_est(resultados,"menos_tiendas"),
            "balanceado": calc_est(resultados,"balanceado"),
        }
    })


# ─── INICIO ───────────────────────────────────────────────────────────────────
print("\n🦷 OdontoPrecio iniciando...")
print(f"  GitHub Raw URL: {GITHUB_RAW_URL}")
cargar_productos_inicial()

# Thread de verificación cada 15 minutos
threading.Thread(target=verificar_actualizacion, daemon=True).start()
print("  Verificación automática cada 15 minutos iniciada\n")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"📡 http://localhost:{port}\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
