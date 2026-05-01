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
_file_lock = threading.Lock()

def get_productos():
    if _cache["productos"] is None:
        _cache["productos"] = cargar_productos()
        _cache["nombres_norm"] = None
    return _cache["productos"]

def get_nombres_norm():
    return get_nombres_norm_con_indice()

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
import unicodedata
from collections import defaultdict

STOPWORDS = {"de","el","la","lo","los","las","en","con","por","para","y","o","e","un","una","x","a"}
MIN_FUZZY = 72

SINONIMOS_GRUPOS = [
    {"composite","resina","compomero","restaurador"},
    {"anestesia","anescart","carpule","mepivacaina","lidocaina","articaina",
     "scandicaine","mepinor","alphacaine","ultracaine","septocaine"},
    {"gutapercha","guttapercha","guta","conos gutapercha","puntas gutapercha"},
    {"lima","limas","endodoncia","protaper","waveone","reciproc","mtwo"},
    {"fresa","fresas","turbina","micromotor","contraangulo"},
    {"bracket","brackets","ortodoncia","arco","alambre"},
    {"adhesivo","bond","primer","bonding"},
    {"cemento","ionomero","ionómero","relyx","panavia","multilink"},
    {"blanqueamiento","blanqueador","whitening","peroxido"},
    {"impresion","alginato","silicona","vinilpolisiloxano","putty"},
    {"guante","guantes","latex","nitrilo","bioseguridad"},
    {"radiografia","rx","pelicula","placa radiografica"},
    {"poste","perno","fibra de vidrio"},
    {"sellante","sellador","fisuras"},
    {"yeso","escayola","piedra dental"},
    {"protesis","acrilico","dentadura"},
    {"banda de matriz","rollo de matriz","tofflemire","palodent"},
    {"hipoclorito","irrigante","edta","irrigacion"},
    {"cirugia","bisturi","suturas","periodoncia"},
    {"implante","implantologia","pilar","tornillo"},
]

def _norm_sin(s):
    t = unicodedata.normalize("NFD", s.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r" +", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()

_SINONIMOS_MAP = {}
for _grupo in SINONIMOS_GRUPOS:
    for _termino in _grupo:
        _tn = _norm_sin(_termino)
        _SINONIMOS_MAP[_tn] = {_norm_sin(s) for s in _grupo if s != _termino}

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

# ─── ÍNDICE INVERTIDO ─────────────────────────────────────────────────────────
_indice: dict = {}
_nombres_norm_cache: list = []

def construir_indice(productos):
    global _indice, _nombres_norm_cache
    indice = defaultdict(set)
    nombres_norm = []
    for i, p in enumerate(productos):
        norm = normalizar(p["nombre"])
        nombres_norm.append(norm)
        tokens = [t for t in norm.split() if t not in STOPWORDS and len(t) > 1]
        for token in tokens:
            stem = stemming_basico(token)
            indice[token].add(i)
            if stem != token:
                indice[stem].add(i)
            for sin in _SINONIMOS_MAP.get(token, set()):
                indice[f"__sin__{sin}"].add(i)
    _indice = dict(indice)
    _nombres_norm_cache = nombres_norm
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
        if stem in _indice:  candidatos |= _indice[stem]
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

# Marcas conocidas — si aparecen en el query actúan como filtro duro
# (el producto DEBE contener la marca para aparecer en resultados)
_MARCAS = {
    '3m','ivoclar','dentsply','angelus','gc','kavo','sirona','voco',
    'kerr','ultradent','ormco','american orthodontics','ormco',
    'medibase','rekosept','septodont','molteni','zhermack','bego',
    'woodpecker','satelec','acteon','bien air','nsk','w&h','morita',
    'hu-friedy','hufriedy','hu friedy','american eagle',
    'danaher','solventum','espe',
}

def busqueda_exacta(q_norm, productos, nombres_norm):
    tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    if not tokens: return []

    # Detectar marcas en el query — actúan como filtro duro
    marcas_en_query = [t for t in tokens if t in _MARCAS]

    candidatos_idx = busqueda_por_indice(tokens)
    if candidatos_idx is not None:
        resultados = [productos[i] for i in sorted(candidatos_idx)]
    else:
        patrones = [re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])") for t in tokens]
        resultados = []
        for i, nombre in enumerate(nombres_norm):
            nombre_junto = nombre.replace(" ", "")
            if all(p.search(nombre) or tokens[j] in nombre_junto for j, p in enumerate(patrones)):
                resultados.append(productos[i])

    # Filtro duro de marca: si el query tiene marca, solo devolver productos con esa marca
    if marcas_en_query:
        def tiene_marca(p):
            n = normalizar(p["nombre"])
            return any(m in n or m in n.replace(" ","") for m in marcas_en_query)
        resultados_con_marca = [p for p in resultados if tiene_marca(p)]
        # Solo aplicar el filtro si hay resultados — si no, devolver todo (evitar cero resultados)
        if resultados_con_marca:
            return resultados_con_marca

    return resultados

def score_fuzzy(q_norm, nombre_norm):
    tokens_q = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 2]
    if not tokens_q: return 0
    nombre_junto = nombre_norm.replace(" ", "")
    alguno_presente = any(
        any(tq in tn or tn in tq for tn in nombre_norm.split()) or tq in nombre_junto
        for tq in tokens_q
    )
    if not alguno_presente: return 0
    return max(int(fuzz.partial_ratio(q_norm, nombre_norm)),
               int(fuzz.token_set_ratio(q_norm, nombre_norm)))

def busqueda_fuzzy(q_norm, productos, nombres_norm, excluir_ids=None):
    excluir = excluir_ids or set()
    resultados = []
    for i, nombre in enumerate(nombres_norm):
        p = productos[i]
        if p["id"] in excluir: continue
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
    with _file_lock:
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
    with _file_lock:
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
        return jsonify({"resultados": [], "total": 0, "offset": 0, "limit": 30,
                        "sugerencia": None, "aviso": None})
    if len(q) > 100:
        return jsonify({"error": "Query demasiado larga"}), 400

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

    # Aviso si query muy genérico (1 token corto y muchos resultados)
    tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    aviso = None
    if len(tokens) == 1 and total > 200:
        aviso = "Agregá marca, modelo o medida para resultados más precisos"

    # Sugerencia si no hay resultados exactos pero sí fuzzy
    sugerencia = None
    if not exactos and fuzzy:
        mejor = fuzzy[0]["nombre"]
        sugerencia = f"¿Buscabas: {mejor[:50]}?"

    return jsonify({
        "resultados": todos[offset:offset+limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        "aviso": aviso,
        "sugerencia": sugerencia,
    })

@app.route("/api/autocomplete")
def autocomplete():
    """Sugerencias rápidas mientras el usuario escribe (máx 6 resultados)."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    q_norm = normalizar(q)
    tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
    if not tokens:
        return jsonify([])

    productos = get_productos()
    nombres_norm = get_nombres_norm()

    # Buscar por prefijo en el índice (rápido)
    candidatos_idx = busqueda_por_indice(tokens)
    if candidatos_idx is None:
        return jsonify([])

    # Armar sugerencias únicas por nombre normalizado
    vistos = set()
    sugerencias = []
    for i in sorted(candidatos_idx):
        p = productos[i]
        nombre = p["nombre"]
        norm_key = nombre.lower()[:40]
        if norm_key in vistos:
            continue
        vistos.add(norm_key)
        sugerencias.append({
            "nombre": nombre,
            "tienda": p["tienda_nombre"],
            "precio_fmt": p["precio_fmt"],
        })
        if len(sugerencias) >= 6:
            break

    return jsonify(sugerencias)

@app.route("/api/estado")
def estado():
    """Estado general del sistema — para el header de confianza."""
    from datetime import datetime
    productos = get_productos()
    por_tienda = {}
    for p in productos:
        t = p["tienda_nombre"]
        por_tienda[t] = por_tienda.get(t, 0) + 1

    # Leer reporte de scraping si existe
    reporte_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reporte_scraping.json")
    tiendas_ok = len([t for t in TIENDAS])
    tiendas_error = 0
    ultima_actualizacion = None
    ultima_fmt = "No disponible"

    if os.path.exists(reporte_path):
        try:
            with open(reporte_path, encoding="utf-8") as f:
                rep = json.load(f)
            ultima_actualizacion = rep.get("fecha", "")
            tiendas_ok = sum(1 for t in rep.get("tiendas", []) if t.get("estado") in ("ok", "bajo"))
            tiendas_error = sum(1 for t in rep.get("tiendas", []) if t.get("estado") in ("error_fatal", "sin_productos"))
            # Formatear fecha
            if ultima_actualizacion:
                try:
                    dt = datetime.strptime(ultima_actualizacion, "%Y-%m-%d %H:%M:%S")
                    hoy = datetime.now().date()
                    if dt.date() == hoy:
                        ultima_fmt = f"hoy {dt.strftime('%H:%M')}"
                    else:
                        ultima_fmt = dt.strftime("%d/%m %H:%M")
                except Exception:
                    ultima_fmt = ultima_actualizacion[:16]
        except Exception:
            pass
    elif os.path.exists(HIST_PATH):
        # Fallback: usar fecha de modificación del historial
        try:
            mod = os.path.getmtime(HIST_PATH)
            dt = datetime.fromtimestamp(mod)
            hoy = datetime.now().date()
            if dt.date() == hoy:
                ultima_fmt = f"hoy {dt.strftime('%H:%M')}"
            else:
                ultima_fmt = dt.strftime("%d/%m %H:%M")
        except Exception:
            pass

    tiendas_totales = len(TIENDAS)

    return jsonify({
        "total_productos": len(productos),
        "tiendas_totales": tiendas_totales,
        "tiendas_ok": tiendas_ok,
        "tiendas_error": tiendas_error,
        "ultima_actualizacion": ultima_actualizacion,
        "ultima_fmt": ultima_fmt,
        "texto_header": f"{len(productos):,} productos · {tiendas_ok}/{tiendas_totales} tiendas · actualizado {ultima_fmt}".replace(",", "."),
    })

@app.route("/api/historial/<producto_id>")
def historial_producto(producto_id):
    hist = get_historial()
    entradas = hist.get(producto_id, [])
    # Calcular variación vs hace 30 días
    variacion = None
    precio_30d = None
    if len(entradas) >= 2:
        actual = entradas[-1]["precio"]
        # Buscar entrada más cercana a 30 días atrás
        from datetime import datetime, timedelta
        hace_30 = datetime.now() - timedelta(days=30)
        for e in reversed(entradas[:-1]):
            try:
                fecha_e = datetime.strptime(e["fecha"], "%Y-%m-%d")
                if fecha_e <= hace_30 + timedelta(days=5):
                    precio_30d = e["precio"]
                    if precio_30d > 0:
                        variacion = round(((actual - precio_30d) / precio_30d) * 100, 1)
                    break
            except Exception:
                pass
    return jsonify({
        "entradas": entradas,
        "precio_30d": precio_30d,
        "variacion_pct": variacion,
    })


# ─── PARSER UNIVERSAL DE ATRIBUTOS ───────────────────────────────────────────
#
# Extrae atributos estructurados de cualquier texto de producto odontológico.
# Sin reglas por producto — trabaja por patrones léxicos universales.
#

# Drogas anestésicas — vocabulario técnico fijo del dominio
_DROGAS = {
    'mepivacaina','lidocaina','articaina','bupivacaina','prilocaina',
    'scandicaine','alphacaine','mepinor','anescart','ultracaine','septocaine',
    'xylestesin','novocaina','carticaina','mepivastesin',
}

# Materiales de guantes/barreras (par opuesto: penaliza si difieren)
_MATERIALES = [
    'nitrilo','latex','vinilo','neopreno','silicona','acrilico',
    'carbide','diamante','acero','metal','fibra','papel','algodon',
    'ceramica','circonio','titanio','cobalto',
]

# Colores
_COLORES = [
    'negro','blanco','azul','rojo','verde','amarillo',
    'naranja','transparente','natural','rosado','violeta',
]

# Pesos de cada atributo: cuánto suma un match y cuánto penaliza un conflicto
_PESOS = {
    'tono':       {'match': 30, 'conflict': -65},  # A3≠A2 = crítico
    'modelo':     {'match': 25, 'conflict': -65},  # Z350≠Z250 — penalización fuerte
    'talle':      {'match': 20, 'conflict': -55},  # M≠L
    'material':   {'match': 15, 'conflict': -55},  # nitrilo≠latex
    'calibre':    {'match': 25, 'conflict': -60},  # #25≠#35
    'droga':      {'match': 20, 'conflict': -60},  # mepivacaina≠articaina
    'porcentaje': {'match': 10, 'conflict': -35},
    'dilucion':   {'match': 10, 'conflict': -30},
    'color':      {'match':  5, 'conflict': -20},
    'cantidad':   {'match':  3, 'conflict':  -8},
    'medidas':    {'match': 12, 'conflict': -30},
}

_STOP_ATTRS = {
    'de','el','la','los','las','en','con','por','para','y','o','un','una',
    'x','talle','talla','tipo','nro','num','iso','mas','plus','pro',
    'kit','pack','set','caja','frasco','jeringa','compula','unidad',
    'unidades','caja','bolsa','rollo','tubo','sobre',
}

def _extraer_atributos(texto):
    """
    Parser universal de atributos odontológicos.
    Sin hardcodeo por producto — trabaja por patrones léxicos.
    """
    t = normalizar(texto)
    t_orig = texto
    attrs = {}

    # ── TONO dental: A1, A2, A3, B1, C2, D3, A3.5, etc. ──
    tonos = re.findall(r'\b([a-d][0-9](?:[.,][0-9])?)\b', t)
    if tonos: attrs['tono'] = tonos[0]

    # ── MODELO alfanumérico: Z350, Z250, P60, Z100, XT, etc. ──
    modelos = re.findall(r'\b([a-z]{1,5}\d{2,4}(?:[a-z]{0,4})?)\b', t)
    modelos = [m for m in modelos
               if not re.match(r'^(iso|nro|num|the|and|con|pro|mas|x\d+)$', m)
               and len(m) >= 3]
    if modelos: attrs['modelo'] = modelos[0]

    # ── MEDIDAS con unidad: 25mm, 4g, 8ml, 1kg, etc. ──
    medidas = re.findall(r'\b(\d+(?:[.,]\d+)?\s*(?:mm|ml|g|kg|cm|l|cc|ul))\b', t)
    if medidas:
        attrs['medidas'] = sorted(set(m.replace(' ', '') for m in medidas))

    # ── PORCENTAJE: 3%, 5.25%, 0.12% ──
    porcs = re.findall(r'\b(\d+(?:[.,]\d+)?)\s*%', t)
    if porcs: attrs['porcentaje'] = porcs[0]

    # ── TALLE: M, L, XL, S, XS ──
    talle = re.search(r'\b(?:talle\s*|talla\s*|size\s*)?([xX]{0,2}[sSlLmM])\b(?!\w)', t)
    if talle: attrs['talle'] = talle.group(1).upper()

    # ── CANTIDAD: x50, x100, x5, 50 unidades ──
    cant = re.search(r'\bx\s*(\d+)\b', t)
    if not cant:
        cant = re.search(r'\b(\d+)\s*(?:unidades|unid|u\b|caps?|carpules?)', t)
    if cant: attrs['cantidad'] = int(cant.group(1))

    # ── CALIBRE de instrumento: #25, ISO 25, nro 15 ──
    calib = re.search(r'#\s*(\d{1,3})\b', t_orig)
    if not calib: calib = re.search(r'\biso\s*(\d{1,3})\b', t)
    if not calib: calib = re.search(r'\bnro?\.?\s*(\d{1,3})\b', t)
    if calib: attrs['calibre'] = calib.group(1)

    # ── DILUCIÓN: 1:100000, 1:80000 ──
    dil = re.search(r'1\s*:\s*(\d+)', t_orig)
    if dil: attrs['dilucion'] = f"1:{dil.group(1)}"

    # ── DROGA anestésica ──
    for droga in _DROGAS:
        if re.search(r'\b' + droga[:6] + r'\w*\b', t):
            attrs['droga'] = droga
            break

    # ── MATERIAL ──
    for mat in _MATERIALES:
        if re.search(r'\b' + mat[:5] + r'\w*\b', t):
            attrs['material'] = mat
            break

    # ── COLOR ──
    for col in _COLORES:
        if re.search(r'\b' + col[:4] + r'\w*\b', t):
            attrs['color'] = col
            break

    # ── TOKENS SEMÁNTICOS (lo que queda) ──
    attrs['tokens'] = [
        tok for tok in t.split()
        if len(tok) > 1
        and tok not in _STOP_ATTRS
        and not re.match(r'^\d+(?:mm|ml|g|kg|%|cm)?$', tok)
        and not re.match(r'^\d+$', tok)
    ]

    return attrs


def _score_atributos(q_attrs, p_attrs, q_norm, p_norm):
    """
    Score final = fuzzy_base + cobertura_tokens + bonus_atributos - penalizacion_conflictos.
    Devuelve (score_0_100, base, detalles_list).

    El score base combina:
    1. token_set_ratio / partial_ratio (similitud general)
    2. Penalización por tokens importantes del query que NO están en el producto
       Esto evita que "COMPOSITE ULTRA FILL A3" matchee "Composite 3M P60 A3"
       solo porque comparten "composite" y "a3".
    """
    base_fuzzy = max(
        int(fuzz.token_set_ratio(q_norm, p_norm)),
        int(fuzz.partial_ratio(q_norm, p_norm)),
    )

    # Tokens importantes del query (excluye stopwords y tokens cortos/genéricos)
    STOPWORDS_LOCAL = {"de","el","la","los","las","en","con","por","para","y","o",
                       "e","un","una","x","a","composite","resina","adhesivo","cemento",
                       "guante","lima","fresa","bracket","disco","anestesia"}
    q_tokens_imp = [t for t in q_norm.split()
                    if len(t) >= 3 and t not in STOPWORDS_LOCAL
                    and not re.match(r'^\d+$', t)]

    # Calcular cobertura: ¿cuántos tokens importantes del query están en el producto?
    p_junto = p_norm.replace(" ", "")
    tokens_presentes = sum(1 for t in q_tokens_imp if t in p_norm or t in p_junto)
    tokens_ausentes = len(q_tokens_imp) - tokens_presentes

    # Penalizar por tokens importantes ausentes (cada uno resta ~8 puntos del base)
    penalizacion_cobertura = tokens_ausentes * 8 if q_tokens_imp else 0
    base = max(0, base_fuzzy - penalizacion_cobertura)

    bonus = 0
    penalizacion = 0
    detalles = []

    for attr, pesos in _PESOS.items():
        q_val = q_attrs.get(attr)
        p_val = p_attrs.get(attr)
        if q_val is None or p_val is None:
            continue

        if attr == 'medidas':
            q_set = set(q_val) if isinstance(q_val, list) else {q_val}
            p_set = set(p_val) if isinstance(p_val, list) else {p_val}
            if q_set & p_set:
                bonus += pesos['match']
                detalles.append(f"+{attr}:{list(q_set)[0]}")
            elif q_set and p_set:
                penalizacion += abs(pesos['conflict'])
                detalles.append(f"✗{attr}:{list(q_set)[0]}≠{list(p_set)[0]}")
        else:
            if str(q_val).lower().strip() == str(p_val).lower().strip():
                bonus += pesos['match']
                detalles.append(f"+{attr}:{q_val}")
            else:
                penalizacion += abs(pesos['conflict'])
                detalles.append(f"✗{attr}:{q_val}≠{p_val}")

    score = max(0, min(100, base + bonus - penalizacion))
    return score, base, detalles

@app.route("/api/compra-inteligente", methods=["POST"])
def compra_inteligente():
    """
    Recibe lista de líneas y resuelve la mejor compra.
    Para cada línea busca el mejor match y arma 3 estrategias de compra.
    """
    data = request.get_json(silent=True) or {}
    lineas_raw = str(data.get("lista", "")).strip().split("\n")
    lineas = [l.strip() for l in lineas_raw if l.strip() and len(l.strip()) > 1][:30]

    if not lineas:
        return jsonify({"error": "Lista vacía"}), 400

    productos = get_productos()
    nombres_norm = get_nombres_norm()

    def buscar_linea(linea):
        """
        Motor universal de matching para Compra Inteligente.

        Diferencia clave vs búsqueda normal:
        - La búsqueda normal requiere TODOS los tokens presentes (alta precisión)
        - Compra Inteligente usa búsqueda por CUALQUIER token importante + scoring
          con penalización para filtrar. Así encuentra "Filtek P60 A3" aunque el
          producto se llame "Composite Filtek 3M P60 A3 x 4gr" (tokens extra no importan).
        """
        q_norm = normalizar(linea)
        tokens = [t for t in q_norm.split() if t not in STOPWORDS and len(t) > 1]
        if not tokens:
            return {"linea": linea, "matches": [], "generica": True,
                    "aviso": "Línea muy genérica — agregá nombre de producto"}

        es_generica = len(tokens) == 1 and len(tokens[0]) <= 5
        q_attrs = _extraer_atributos(linea)

        # ── PASO 1: Candidatos usando OR de tokens (permisivo) ──
        # En lugar de AND (todos los tokens), usamos unión — cualquier token
        # que matchee en el índice hace que el producto sea candidato.
        # El scoring con penalización se encarga del filtrado fino.
        candidatos_idx = set()

        # Tokens "ancla" — los más específicos/discriminantes
        # Priorizamos tokens largos o alfanuméricos (marca, modelo)
        tokens_ordenados = sorted(tokens, key=lambda t: (
            -len(t),                          # más largo primero
            0 if re.search(r'[0-9]', t) else 1,  # con números primero (z350, p60)
        ))

        for token in tokens_ordenados:
            stem = stemming_basico(token)
            # Buscar en el índice por token exacto y prefijo
            nuevos = set()
            if token in _indice: nuevos |= _indice[token]
            if stem in _indice: nuevos |= _indice[stem]
            if len(token) >= 3:
                for key in _indice:
                    if key.startswith(token) and not key.startswith("__sin__"):
                        nuevos |= _indice[key]
            candidatos_idx |= nuevos

        # Si hay marcas en el query, aplicar filtro duro de marca
        marcas_en_query = [t for t in tokens if t in _MARCAS]
        if marcas_en_query:
            idx_con_marca = set()
            for m in marcas_en_query:
                if m in _indice: idx_con_marca |= _indice[m]
                for key in _indice:
                    if key.startswith(m) and not key.startswith("__sin__"):
                        idx_con_marca |= _indice[key]
            if idx_con_marca:
                candidatos_idx = candidatos_idx & idx_con_marca if candidatos_idx else idx_con_marca

        # Si hay tokens muy específicos (modelo alfanumérico), filtrar para que
        # al menos uno esté presente
        tokens_especificos = [t for t in tokens_ordenados
                               if (len(t) >= 4 or re.search(r'[0-9]', t))
                               and t not in _MARCAS]
        if tokens_especificos and len(candidatos_idx) > 500:
            idx_especificos = set()
            for t in tokens_especificos[:3]:
                stem = stemming_basico(t)
                if t in _indice: idx_especificos |= _indice[t]
                if stem in _indice: idx_especificos |= _indice[stem]
                if len(t) >= 3:
                    for key in _indice:
                        if key.startswith(t) and not key.startswith("__sin__"):
                            idx_especificos |= _indice[key]
            if idx_especificos:
                candidatos_idx = idx_especificos

        # Fallback si el índice no encontró nada
        if not candidatos_idx:
            for i, nombre in enumerate(nombres_norm):
                s = max(int(fuzz.partial_ratio(q_norm, nombre)),
                        int(fuzz.token_set_ratio(q_norm, nombre)))
                if s >= 50:
                    candidatos_idx.add(i)

        if not candidatos_idx:
            return {"linea": linea, "matches": [], "generica": es_generica,
                    "aviso": "No encontramos coincidencias — probá con otro término"}

        # ── PASO 2: Scoring universal para cada candidato ──
        scored = []
        for i in candidatos_idx:
            p = productos[i]
            p_norm = nombres_norm[i]
            p_attrs = _extraer_atributos(p["nombre"])

            # Score base fuzzy
            base = max(
                int(fuzz.token_set_ratio(q_norm, p_norm)),
                int(fuzz.partial_ratio(q_norm, p_norm)),
            )

            # Aplicar scoring de atributos (penaliza conflictos)
            score, _, detalles = _score_atributos(q_attrs, p_attrs, q_norm, p_norm)

            # Umbral mínimo: debe tener al menos base >= 45
            if base >= 45 and score >= 25:
                scored.append((score, base, detalles, p))

        if not scored:
            return {"linea": linea, "matches": [], "generica": es_generica,
                    "aviso": "No encontramos coincidencias exactas"}

        # Ordenar: score desc, luego precio asc
        scored.sort(key=lambda x: (-x[0], x[3]["precio"]))

        # ── PASO 3: Armar matches con clasificación de confianza ──
        matches = []
        for score, base, detalles, p in scored[:5]:
            conflictos = [d for d in detalles if d.startswith("✗")]

            if score >= 80 and not conflictos:
                nivel = "alta"
            elif score >= 55 and len(conflictos) <= 1:
                nivel = "media"
            else:
                nivel = "baja"

            # Detectar si el query pedía tono/tipo pero el producto no lo especifica
            # (el producto tiene variantes — el usuario tiene que elegir en la tienda)
            nota_variante = None
            q_tono = q_attrs.get("tono")
            p_tono = p_attrs.get("tono")
            if q_tono and p_tono is None:
                nota_variante = f"Verificar tono {q_tono.upper()} en tienda"

            matches.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "tienda": p["tienda_nombre"],
                "tienda_slug": p["tienda_slug"],
                "precio": p["precio"],
                "precio_fmt": p["precio_fmt"],
                "url": p.get("url", ""),
                "confianza": score,
                "confianza_nivel": nivel,
                "detalles_match": detalles[:4],
                "conflictos": conflictos,
                "nota_variante": nota_variante,
            })

        aviso = None
        if es_generica:
            aviso = "Agregá marca, modelo o detalle para mejores resultados"
        elif matches and matches[0]["confianza_nivel"] == "baja":
            aviso = "No encontramos coincidencia exacta — mostramos opciones similares"
        elif matches and matches[0]["conflictos"]:
            aviso = f"Atención: {', '.join(matches[0]['conflictos'][:2])}"

        return {
            "linea": linea,
            "matches": matches,
            "generica": es_generica,
            "aviso": aviso,
        }

    resultados = [buscar_linea(l) for l in lineas]

    # Construir las 3 estrategias de compra
    def estrategia_mas_barato(resultados):
        """El producto más barato para cada línea, sin importar tienda."""
        total = 0
        tiendas_usadas = set()
        items = []
        for r in resultados:
            if not r["matches"]:
                items.append(None)
                continue
            mejor = min((m for m in r["matches"] if m["precio"] > 0), key=lambda m: m["precio"], default=None)
            if mejor:
                items.append(mejor)
                total += mejor["precio"]
                tiendas_usadas.add(mejor["tienda"])
            else:
                items.append(None)
        return {"items": items, "total": total, "n_tiendas": len(tiendas_usadas),
                "tiendas": list(tiendas_usadas)}

    def estrategia_menos_tiendas(resultados):
        """Concentrar la compra en la menor cantidad de tiendas posible."""
        from collections import Counter
        # Contar qué tienda aparece más como opción barata
        tienda_scores = Counter()
        for r in resultados:
            for m in r["matches"][:3]:
                if m["precio"] > 0:
                    tienda_scores[m["tienda"]] += 1

        if not tienda_scores:
            return estrategia_mas_barato(resultados)

        tienda_principal = tienda_scores.most_common(1)[0][0]
        total = 0
        tiendas_usadas = set()
        items = []
        for r in resultados:
            if not r["matches"]:
                items.append(None)
                continue
            # Preferir la tienda principal, si no está disponible usar el más barato
            de_tienda = [m for m in r["matches"] if m["tienda"] == tienda_principal and m["precio"] > 0]
            if de_tienda:
                mejor = min(de_tienda, key=lambda m: m["precio"])
            else:
                mejor = min((m for m in r["matches"] if m["precio"] > 0),
                           key=lambda m: m["precio"], default=None)
            if mejor:
                items.append(mejor)
                total += mejor["precio"]
                tiendas_usadas.add(mejor["tienda"])
            else:
                items.append(None)
        return {"items": items, "total": total, "n_tiendas": len(tiendas_usadas),
                "tiendas": list(tiendas_usadas)}

    def estrategia_balanceada(resultados):
        """Top 2 tiendas con más productos disponibles."""
        from collections import Counter
        tienda_scores = Counter()
        for r in resultados:
            for m in r["matches"][:3]:
                if m["precio"] > 0:
                    tienda_scores[m["tienda"]] += 1
        top2 = {t for t, _ in tienda_scores.most_common(2)}
        total = 0
        tiendas_usadas = set()
        items = []
        for r in resultados:
            if not r["matches"]:
                items.append(None)
                continue
            de_top2 = [m for m in r["matches"] if m["tienda"] in top2 and m["precio"] > 0]
            if de_top2:
                mejor = min(de_top2, key=lambda m: m["precio"])
            else:
                mejor = min((m for m in r["matches"] if m["precio"] > 0),
                           key=lambda m: m["precio"], default=None)
            if mejor:
                items.append(mejor)
                total += mejor["precio"]
                tiendas_usadas.add(mejor["tienda"])
            else:
                items.append(None)
        return {"items": items, "total": total, "n_tiendas": len(tiendas_usadas),
                "tiendas": list(tiendas_usadas)}

    est_barato = estrategia_mas_barato(resultados)
    est_tiendas = estrategia_menos_tiendas(resultados)
    est_balance = estrategia_balanceada(resultados)

    return jsonify({
        "lineas": resultados,
        "estrategias": {
            "mas_barato": est_barato,
            "menos_tiendas": est_tiendas,
            "balanceado": est_balance,
        }
    })

@app.route("/api/actualizar", methods=["POST"])
def actualizar():
    clave = request.args.get("clave", "")
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE:
        return jsonify({"error": "No autorizado"}), 403
    def _run():
        nuevos = correr_scraper()
        _cache["productos"] = nuevos
        _cache["nombres_norm"] = None
        global _nombres_norm_cache, _indice
        _nombres_norm_cache = []
        _indice = {}
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Actualizando en segundo plano..."})

@app.route("/api/reporte", methods=["POST"])
def reporte():
    data = request.get_json(silent=True) or {}
    producto_id = str(data.get("id", ""))[:50]
    nombre = str(data.get("nombre", ""))[:200]
    tienda = str(data.get("tienda", ""))[:100]
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
    ADMIN_CLAVE = os.environ.get("ADMIN_CLAVE")
    if not ADMIN_CLAVE or clave != ADMIN_CLAVE:
        return "Acceso denegado", 403
    if not os.path.exists(REPORTES_PATH):
        return "No hay reportes todavia.", 200
    try:
        import csv, io
        with open(REPORTES_PATH, encoding="utf-8") as f:
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

@app.route("/api/reporte-scraping")
def reporte_scraping():
    reporte_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reporte_scraping.json")
    if not os.path.exists(reporte_path):
        return jsonify({"error": "No hay reporte disponible aún."}), 404
    with open(reporte_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


_actualizar_si_es_necesario()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"\n🦷 OdontoPrecio arrancando en puerto {port}...")
    if debug:
        print(f"📡 Abrí tu navegador en: http://localhost:{port}\n")
    app.run(debug=debug, host="0.0.0.0", port=port)
