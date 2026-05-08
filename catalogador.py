"""
catalogador.py — Extrae atributos estructurados de nombres de productos odontológicos.

No hay reglas por producto específico.
Trabaja por patrones léxicos universales que cubren todo el catálogo dental.

Uso:
    from catalogador import catalogar, clasificar_tokens
    attrs = catalogar("Composite Filtek Z350 XT 3M A3 4gr")
    tokens = clasificar_tokens("anestesia anescart forte")
"""

import re
import unicodedata


# ─── NORMALIZACIÓN ────────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[-./\\()%,;:!?\\[\\]]", " ", t)
    return re.sub(r" +", " ", t).strip()


# ─── VOCABULARIOS ─────────────────────────────────────────────────────────────

# Marcas comerciales
_MARCAS = {
    "3m", "ivoclar", "dentsply", "angelus", "gc", "kavo", "sirona", "voco",
    "kerr", "ultradent", "ormco", "medibase", "septodont", "zhermack", "bego",
    "woodpecker", "satelec", "nsk", "morita", "hu-friedy", "asa dental",
    "american orthodontics", "american eagle", "solventum", "espe", "maillefer",
    "coltene", "shofu", "tokuyama", "bisco", "sun medical", "parkell",
    "procter", "colgate", "oral b", "philips", "braun",
    # Marcas locales / argentinas
    "anescart", "alphacaine", "mepinor", "scandicaine", "ultracaine", "citoject",
    "klepp", "delta", "metabiomed", "reciproc", "becht", "gapadent", "diadent",
}

# Modelos con marca implícita
_MODELO_MARCA = {
    # 3M / Solventum
    "p60": "3m", "z350": "3m", "z250": "3m", "z100": "3m",
    "filtek": "3m", "supreme": "3m", "silorane": "3m",
    "single bond": "3m", "scotchbond": "3m", "adper": "3m",
    "ketac": "3m", "relyx": "3m", "espe": "3m",
    # Ivoclar
    "tetric": "ivoclar", "empress": "ivoclar", "ips": "ivoclar",
    "vivadent": "ivoclar", "multilink": "ivoclar", "variolink": "ivoclar",
    # Dentsply / Maillefer
    "protaper": "dentsply", "waveone": "dentsply",
    "maillefer": "dentsply", "smartlite": "dentsply", "aquasil": "dentsply",
    "caulk": "dentsply", "nupro": "dentsply",
    # Angelus
    "mta angelus": "angelus", "fillcanal": "angelus",
    # GC
    "fuji": "gc", "g-aenial": "gc", "gradia": "gc",
    # Kerr
    "herculite": "kerr", "harmonize": "kerr", "maxcem": "kerr",
    "nexus": "kerr", "optibond": "kerr",
    # Voco
    "grandio": "voco", "ionolux": "voco",
    # Ultradent
    "opalescence": "ultradent",
    # SDI
    "luna": "sdi", "riva": "sdi",
    # Coltene
    "brilliant": "coltene", "synergy": "coltene",
    # American Orthodontics
    "roth": "american orthodontics", "mbt": "american orthodontics",
    # Ormco
    "damon": "ormco",
}

# ─── TIPOS DE PRODUCTO ────────────────────────────────────────────────────────
# IMPORTANTE: el orden importa — más específico primero.
# "cono de papel" → papel, "cono gutapercha" → gutapercha, "cono" solo → ambiguo
_TIPOS = {
    "composite": "composite",
    "resina": "composite",
    "compomero": "composite",
    "restaurador": "composite",
    "anestesia": "anestesia",
    "carpule": "anestesia",
    "cartucho": "anestesia",
    "fresa": "fresa",
    "piedra": "fresa",
    "guante": "guantes",
    "guantes": "guantes",
    "adhesivo": "adhesivo",
    "bond": "adhesivo",
    "primer": "adhesivo",
    "cemento": "cemento",
    "ionomero": "cemento",
    "ionómero": "cemento",
    "gutapercha": "cono_gutapercha",
    "guttapercha": "cono_gutapercha",
    "guta": "cono_gutapercha",
    # "cono" y "conos" SIN "papel" → gutapercha (lo más común en endodoncia)
    # Con "papel" → cono_papel (se resuelve abajo con lógica especial)
    "alginato": "alginato",
    "silicona": "silicona",
    "yeso": "yeso",
    "escayola": "yeso",
    "bracket": "bracket",
    "arco": "arco_orto",
    "alambre": "arco_orto",
    "blanqueador": "blanqueamiento",
    "blanqueamiento": "blanqueamiento",
    "sellante": "sellante",
    "sellador": "sellante",
    "hipoclorito": "irrigante",
    "edta": "irrigante",
    "matriz": "matriz",
    "banda": "matriz",
    "poste": "poste",
    "perno": "poste",
    "aguja": "aguja",
    "agujas": "aguja",
    "cubeta": "cubeta",
    "disco": "disco",
    "tira": "tira",
    # Lima — tipo base, el subtipo se extrae por separado
    "lima": "lima",
    "limas": "lima",
    "instrumento endodontico": "lima",
    # Punta de papel — absorbente para secar conducto (distinto de cono obturador)
    "punta de papel": "punta_papel",
    "puntas de papel": "punta_papel",
}

# Drogas anestésicas — NO son intercambiables entre sí
# Un odontólogo que pide "articaina" no quiere "mepivacaina"
_DROGAS = {
    "mepivacaina", "lidocaina", "articaina", "bupivacaina", "prilocaina",
    "carticaina", "scandicaine", "alphacaine", "mepinor", "anescart",
    "ultracaine", "septocaine", "xylestesin", "citoject",
}

# Materiales — no intercambiables
_MATERIALES = [
    "nitrilo", "latex", "vinilo", "neopreno", "silicona",
    "acrilico", "carbide", "diamante", "acero", "metal",
    "fibra", "papel", "algodon", "ceramica", "circonio",
]

# Colores
_COLORES = [
    "negro", "blanco", "azul", "rojo", "verde", "amarillo",
    "naranja", "transparente", "natural", "rosado", "violeta",
]

# Subtipos de composite
_SUBTIPOS_COMPOSITE = {
    "flow": "flow",
    "flowable": "flow",
    "fluido": "flow",
    "bulk": "bulk",
    "posterior": "posterior",
    "anteriores": "anterior",
    "anterior": "anterior",
    "universal": "universal",
    "esmalte": "esmalte",
    "enamel": "esmalte",
    "dentin": "dentina",
    "dentina": "dentina",
    "opaque": "opaco",
    "opaco": "opaco",
}

# ─── SUBTIPOS DE LIMA ─────────────────────────────────────────────────────────
# Las limas K, H (Hedstrom), rotatorias y reciprocantes son instrumentos
# completamente distintos en clínica. No son intercambiables.
#
# Lima K / K-file: acero inox, movimiento vaivén, sección cuadrada,
#                  uso manual universal. Nombre comercial: K-file, Kerr file.
# Lima H / Hedstrom: acero inox, corte en tracción, más agresiva que la K.
# Lima K-flex: variante de K con mayor flexibilidad (sección romboidal).
# Lima Flexofile: variante de K con sección triangular, muy flexible.
# Lima rotatoria NiTi: ProTaper, WaveOne, Reciproc, HyFlex, MTwo, etc.
# Lima reciprocante: WaveOne (1 lima), Reciproc (1 lima), movimiento vaivén motor.

_SUBTIPOS_LIMA = [
    # Rotatorias / reciprocantes (sistemas completos — marca ya las identifica)
    (r"\bprotaper\b",         "rotatoria_protaper"),
    (r"\bwaveone\b",          "reciprocante_waveone"),
    (r"\breciprocante\b",     "reciprocante"),
    (r"\breciprocating\b",    "reciprocante"),
    (r"\breciproc\b",         "reciprocante_reciproc"),
    (r"\bhyflex\b",           "rotatoria_hyflex"),
    (r"\bmtwo\b",             "rotatoria_mtwo"),
    (r"\btf\s?adaptive\b",    "rotatoria_tf"),
    (r"\btwisted\b",          "rotatoria_tf"),
    (r"\bniti\b",             "rotatoria_niti"),
    (r"\bnickel\s*titanio\b", "rotatoria_niti"),
    (r"\bniquel\s*titanio\b", "rotatoria_niti"),
    # Manuales — tipo K
    (r"\blima\s*k\b",         "manual_k"),
    (r"\bk\s*file\b",         "manual_k"),
    (r"\barchivo\s*k\b",      "manual_k"),
    (r"\btipo\s*k\b",         "manual_k"),
    (r"\bk-flex\b",           "manual_k_flex"),
    (r"\bkflex\b",            "manual_k_flex"),
    (r"\bflexofile\b",        "manual_flexofile"),
    # Manuales — tipo H / Hedstrom
    (r"\blima\s*h\b",         "manual_h"),
    (r"\bh\s*file\b",         "manual_h"),
    (r"\bhedstrom\b",         "manual_h"),
    (r"\btipo\s*h\b",         "manual_h"),
    # Reamer / escariador
    (r"\breamer\b",           "manual_reamer"),
    (r"\bescariador\b",       "manual_reamer"),
    # Limas de retratamiento
    (r"\bretratamiento\b",    "retratamiento"),
    (r"\bretreating\b",       "retratamiento"),
    # Si dice "manual" sin más
    (r"\bmanual\b",           "manual"),
]

# Tokens que son SIEMPRE genéricos (nunca específicos en una búsqueda)
_TOKENS_GENERICOS = {
    "composite", "resina", "anestesia", "guante", "guantes",
    "lima", "limas", "fresa", "fresas", "adhesivo", "cemento", "yeso", "poste",
    "bracket", "disco", "tira", "jeringa", "carpule",
    "aguja", "agujas", "cubeta", "alginato", "silicona",
    "blanqueador", "sellante", "hipoclorito", "irrigante",
    "instrumental", "material", "producto", "insumo",
    "dental", "odontologico", "odontológico",
    "para", "sin", "con", "uso", "x",
    # "cono" y "conos" son genéricos solos — se vuelven específicos
    # solo cuando van acompañados de "gutapercha", "papel", etc.
    "cono", "conos", "puntas",
}


# ─── CATALOGADOR ──────────────────────────────────────────────────────────────

def catalogar(nombre_crudo: str) -> dict:
    """
    Extrae atributos estructurados de un nombre de producto odontológico.
    """
    t = normalizar(nombre_crudo)
    orig = nombre_crudo

    attrs = {
        "tipo": None,
        "marca": None,
        "linea": None,
        "modelo": None,
        "subtipo": None,
        "tono": None,
        "color": None,
        "material": None,
        "droga": None,
        "talle": None,
        "calibre": None,
        "longitud": None,
        "peso": None,
        "cantidad": None,
        "presentacion": None,
    }

    # ── TIPO ─────────────────────────────────────────────────────────────────
    # Primero detectar combinaciones específicas antes que palabras sueltas

    # Cono de papel (absorbente, para secar conducto) — debe detectarse ANTES que "cono" solo
    if re.search(r"\bcono[s]?\s+(de\s+)?papel\b|\bpunta[s]?\s+(de\s+)?papel\b|\bpaper\s+point\b", t):
        attrs["tipo"] = "cono_papel"
    # Cono de gutapercha explícito
    elif re.search(r"\bcono[s]?\s+(de\s+)?(gutapercha|guta|guttapercha)\b|\b(gutapercha|guta|guttapercha)\s+cono[s]?\b", t):
        attrs["tipo"] = "cono_gutapercha"
    # "cono" o "conos" solos — en odontología lo más frecuente es gutapercha
    # pero sin calificador lo dejamos como "cono" para no asumir
    elif re.search(r"\bcono[s]?\b", t) and not re.search(r"\bpapel\b", t):
        # Si también menciona gutapercha/guta en cualquier parte → es gutapercha
        if re.search(r"\bgut[a]?p?\w*\b", t):
            attrs["tipo"] = "cono_gutapercha"
        else:
            attrs["tipo"] = "cono_gutapercha"  # Default: en endodoncia "cono" = gutapercha
    else:
        # Resto de tipos por vocabulario
        for palabra, tipo in _TIPOS.items():
            if re.search(r"\b" + re.escape(palabra) + r"\b", t):
                attrs["tipo"] = tipo
                break

    # ── INFERIR TIPO DESDE DROGA ────────────────────────────────────────────────
    # Si el nombre contiene una droga anestésica pero no dijo "anestesia",
    # igual es anestesia (ej: "Articaina 4% x50", "Mepivacaina 3%")
    if not attrs["tipo"]:
        for droga in _DROGAS:
            if re.search(r"\b" + droga[:6] + r"\w*\b", t):
                attrs["tipo"] = "anestesia"
                break

    # ── MARCA ─────────────────────────────────────────────────────────────────
    for marca in sorted(_MARCAS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(marca) + r"\b", t):
            attrs["marca"] = marca
            break
    _es_copia = bool(re.search(r"\b(simil|similar|tipo|estilo|alternativ|generico|equivalente|reforzado\s+para)\b", t))
    if not attrs.get("marca") and not _es_copia:
        for modelo_key, marca_implicita in _MODELO_MARCA.items():
            if re.search(r"\b" + re.escape(modelo_key) + r"\b", t):
                attrs["marca"] = marca_implicita
                break

    # ── LÍNEA COMERCIAL ───────────────────────────────────────────────────────
    lineas_conocidas = [
        "filtek", "tetric", "charisma", "venus", "gradia", "estelite",
        "beautifil", "harmonize", "herculite", "premise", "aelite",
        "protaper", "waveone", "reciproc", "hyflex", "twisted",
        "single bond", "optibond", "scotchbond", "clearfil", "excite",
        "ketac", "vitrebond", "fuji", "ketac molar",
        "relyx", "panavia", "multilink", "nexus",
        "opalescence", "zoom", "beyond", "nitewhite",
        "supreme", "silorane", "p60", "z350", "z250", "z100",
    ]
    # Encontrar TODAS las líneas que matchean, priorizar código de producto
    lineas_encontradas = []
    for linea in sorted(lineas_conocidas, key=len, reverse=True):
        if re.search(r"\b" + re.escape(linea) + r"\b", t):
            lineas_encontradas.append(linea)
    if lineas_encontradas:
        # Preferir códigos alfanuméricos (p60, z350, z250) sobre nombres (filtek, tetric)
        codigos = [l for l in lineas_encontradas if re.match(r'^[a-z]+[0-9]', l)]
        attrs["linea"] = codigos[0] if codigos else lineas_encontradas[0]

    # ── INFERIR TIPO LIMA desde línea conocida de endodoncia ──────────────────
    # "WaveOne Gold", "ProTaper Next", "Reciproc" sin "lima" explícita = lima
    _lineas_lima = {"protaper", "waveone", "reciproc", "hyflex", "mtwo", "twisted", "k3xf"}
    if not attrs["tipo"] and attrs.get("linea") in _lineas_lima:
        attrs["tipo"] = "lima"
    # También inferir por sistema de limas en el nombre aunque no sea linea detectada
    if not attrs["tipo"] and re.search(r"\b(waveone|wave one|protaper|reciproc|hyflex|mtwo)\b", t):
        attrs["tipo"] = "lima"

    # ── MODELO alfanumérico ───────────────────────────────────────────────────
    modelos = re.findall(r"\b([a-z]{1,5}[0-9]{2,4}[a-z]{0,4})\b", t)
    modelos = [m for m in modelos
               if len(m) >= 3
               and not re.match(r"^(iso|pro|con|mas|x\d+|nro|num)$", m)
               and not m.isdigit()]
    if modelos:
        attrs["modelo"] = modelos[0]

    # ── SUBTIPO de lima ───────────────────────────────────────────────────────
    if attrs["tipo"] == "lima" or re.search(r"\blima[s]?\b|\benodod\w+\b", t):
        for patron, subtipo in _SUBTIPOS_LIMA:
            if re.search(patron, t):
                attrs["subtipo"] = subtipo
                break

    # ── INFERIR TIPO COMPOSITE desde modelo/línea conocida ────────────────────
    _lineas_composite = {"p60", "z350", "z250", "z100", "filtek", "supreme",
                         "herculite", "harmonize", "charisma", "venus", "gradia",
                         "tetric", "estelite", "beautifil", "premise"}
    if not attrs["tipo"] and attrs.get("linea") in _lineas_composite:
        attrs["tipo"] = "composite"
    # Modelos con sufijos (z350xt → z350, z250xt → z250)
    _modelo_base = re.sub(r"xt$|flow$|ultra$", "", attrs.get("modelo") or "")
    if not attrs["tipo"] and _modelo_base in {"p60", "z350", "z250", "z100", "z100", "filtek"}:
        attrs["tipo"] = "composite"
        attrs["tipo"] = "composite"

    # ── INFERIR TIPO CEMENTO desde línea conocida ────────────────────────────
    _lineas_cemento = {"ketac", "ketac molar", "vitrebond", "relyx", "fuji",
                       "multilink", "panavia", "nexus", "maxcem"}
    if not attrs["tipo"] and attrs.get("linea") in _lineas_cemento:
        attrs["tipo"] = "cemento"

    # Si detectamos subtipo de lima pero no tipo → asignar tipo lima
    if attrs.get("subtipo") and not attrs["tipo"]:
        if any(sub in (attrs["subtipo"] or "") for sub in
               ["manual_k", "manual_h", "rotatoria", "reciprocante", "retratamiento", "manual"]):
            attrs["tipo"] = "lima"

    # ── SUBTIPO de composite ──────────────────────────────────────────────────
    if attrs["tipo"] == "composite" and not attrs.get("subtipo"):
        for palabra, subtipo in _SUBTIPOS_COMPOSITE.items():
            if re.search(r"\b" + re.escape(palabra) + r"\b", t):
                attrs["subtipo"] = subtipo
                break

    # ── TONO dental (A1, A2, A3, B1, C2, D3, A3.5) ───────────────────────────
    tonos = re.findall(r"\b([a-d][0-9](?:[.,][0-9])?)\b", t)
    if tonos:
        attrs["tono"] = tonos[0]

    # ── MATERIAL ──────────────────────────────────────────────────────────────
    for mat in _MATERIALES:
        if re.search(r"\b" + mat[:5] + r"\w*\b", t):
            attrs["material"] = mat
            break

    # ── COLOR ─────────────────────────────────────────────────────────────────
    for col in _COLORES:
        if re.search(r"\b" + col[:4] + r"\w*\b", t):
            attrs["color"] = col
            break

    # ── DROGA ANESTÉSICA ──────────────────────────────────────────────────────
    # Priorizar drogas genéricas (más largas/específicas) sobre marcas comerciales
    # Orden: primero los nombres genéricos (articaina, mepivacaina, lidocaina),
    # luego los nombres comerciales (anescart, alphacaine, etc.)
    _DROGAS_GENERICAS = ["mepivacaina", "lidocaina", "articaina", "bupivacaina",
                         "prilocaina", "carticaina"]
    _DROGAS_COMERCIALES = ["scandicaine", "alphacaine", "mepinor", "anescart",
                           "ultracaine", "septocaine", "xylestesin", "citoject"]
    droga_detectada = None
    for droga in _DROGAS_GENERICAS:
        if re.search(r"\b" + droga[:6] + r"\w*\b", t):
            droga_detectada = droga
            break
    if not droga_detectada:
        for droga in _DROGAS_COMERCIALES:
            if re.search(r"\b" + droga[:6] + r"\w*\b", t):
                droga_detectada = droga
                break
    if droga_detectada:
        attrs["droga"] = droga_detectada

    # ── TALLE ─────────────────────────────────────────────────────────────────
    talle = re.search(r"\b(?:talle\s*|talla\s*|size\s*)?([xX]{0,2}[sSlLmM])\b(?!\w)", t)
    if talle:
        attrs["talle"] = talle.group(1).upper()

    # ── CALIBRE de instrumento (#25, ISO 25, nro 15) ──────────────────────────
    calib = re.search(r"#\s*(\d{1,3})\b", orig)
    if not calib:
        calib = re.search(r"\biso\s*(\d{1,3})\b", t)
    if not calib:
        calib = re.search(r"\bnro?\.?\s*(\d{1,3})\b", t)
    if calib:
        attrs["calibre"] = calib.group(1)

    # ── LONGITUD ──────────────────────────────────────────────────────────────
    long_m = re.search(r"\b(\d+)\s*mm\b", t)
    if long_m:
        attrs["longitud"] = long_m.group(1) + "mm"

    # ── PESO ──────────────────────────────────────────────────────────────────
    peso_m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(g|gr|kg|ml)\b", t)
    if peso_m:
        attrs["peso"] = peso_m.group(1) + peso_m.group(2)

    # ── CANTIDAD ──────────────────────────────────────────────────────────────
    cant = re.search(r"\bx\s*(\d+)\b", t)
    if not cant:
        cant = re.search(r"\b(\d+)\s*(?:unidades|unid|u\b|caps?|carpules?)", t)
    if cant:
        attrs["cantidad"] = int(cant.group(1))

    # ── PRESENTACIÓN ──────────────────────────────────────────────────────────
    presentaciones = {
        "jeringa": "jeringa", "compula": "compula", "blister": "blister",
        "frasco": "frasco", "tubo": "tubo", "caja": "caja",
        "rollo": "rollo", "sobre": "sobre", "kit": "kit",
        "aplicap": "aplicap", "capsulas": "capsula", "carpule": "carpule",
    }
    for pres, val in presentaciones.items():
        if re.search(r"\b" + re.escape(pres) + r"\b", t):
            attrs["presentacion"] = val
            break

    return {k: v for k, v in attrs.items() if v is not None}


# ─── CLASIFICADOR DE TOKENS ───────────────────────────────────────────────────

def clasificar_tokens(query: str) -> dict:
    """
    Dado un query de usuario, clasifica cada token como ESPECÍFICO o GENÉRICO.

    Lógica:
    - Tokens específicos = marcas, modelos, códigos, tonos, calibres, drogas,
      tipos de lima (K, H), tipos de cono (gutapercha, papel), etc.
    - Tokens genéricos = tipo de producto solo ("lima", "cono", "composite")

    Ejemplos:
      "lima k" → ["lima"] genérico, ["k"] específico
      "limas k file" → ["limas"] genérico, ["k", "file"] específicos
      "conos gutapercha" → ["conos"] genérico, ["gutapercha"] específico
      "conos papel" → ["conos"] genérico, ["papel"] específico
      "composite a3" → ["composite"] genérico, ["a3"] específico
    """
    t = normalizar(query)
    tokens_raw = [tok for tok in t.split() if len(tok) > 1]

    especificos = []
    genericos = []

    for tok in tokens_raw:
        es_marca = tok in _MARCAS
        es_droga = tok in _DROGAS
        tiene_numero = bool(re.search(r"[0-9]", tok))
        es_generico = tok in _TOKENS_GENERICOS
        es_tono = bool(re.match(r"^[a-d][0-9]$", tok))
        es_largo = len(tok) >= 5 and not es_generico

        # Tokens que identifican tipo de lima — son específicos
        es_tipo_lima = tok in {"hedstrom", "flexofile", "rotatoria", "reciprocante",
                               "niti", "manual", "retratamiento", "reamer"}
        # "k" y "h" solos son específicos SOLO en contexto de limas
        # Si van solos sin contexto son ambiguos — los marcamos específicos
        # porque en una búsqueda de productos dentales k/h casi siempre = tipo de lima
        es_letra_lima = tok in {"k", "h"} and len(tok) == 1

        # Tipos de material de cono — específicos
        es_tipo_cono = tok in {"gutapercha", "guta", "guttapercha", "papel", "absorbente"}

        if (es_marca or es_droga or tiene_numero or es_tono
                or es_tipo_lima or es_tipo_cono or es_letra_lima
                or (es_largo and not es_generico)):
            especificos.append(tok)
        else:
            genericos.append(tok)

    return {
        "especificos": especificos,
        "genericos": genericos,
        "todos": tokens_raw,
    }


# ─── SINÓNIMOS ────────────────────────────────────────────────────────────────
#
# REGLA: solo son sinónimos las cosas que un odontólogo considera intercambiables
# cuando busca.
#
# NO son sinónimos:
#   - Drogas anestésicas distintas (articaina ≠ mepivacaina ≠ lidocaina)
#   - Tipos de lima distintos (lima K ≠ lima H ≠ WaveOne)
#   - Cono de papel ≠ cono de gutapercha
#
# SÍ son sinónimos:
#   - Palabras distintas para el mismo objeto ("composite" = "resina")
#   - Variantes ortográficas ("gutapercha" = "guttapercha" = "guta")
#   - Nombres comerciales = nombre genérico cuando son lo mismo

SINONIMOS_GRUPOS = [
    # Composites — distintas palabras para lo mismo
    {"composite", "resina", "compomero", "restaurador"},

    # Anestesia — la palabra genérica, jeringa, carpule
    # NO incluir drogas específicas — articaina ≠ mepivacaina
    {"anestesia", "carpule", "cartucho", "anestesico"},

    # Gutapercha — variantes ortográficas únicamente
    {"gutapercha", "guttapercha", "guta"},
    # Conos de gutapercha — alias del producto
    {"cono gutapercha", "conos gutapercha", "puntas gutapercha", "obturador"},
    # Cono de papel — diferente al de gutapercha
    {"cono papel", "conos papel", "punta papel", "puntas papel", "paper point"},

    # Limas manuales tipo K — variantes del mismo instrumento
    {"lima k", "k file", "kfile", "lima tipo k"},
    # Limas manuales tipo H / Hedstrom — variantes del mismo
    {"lima h", "h file", "hedstrom", "lima tipo h", "lima hedstrom"},
    # Sistemas rotatorios/reciprocantes — solo agrupar alias del mismo sistema
    {"protaper", "pro taper"},
    {"waveone", "wave one", "wave one gold"},
    {"reciproc", "reciprocante"},

    # Fresas — palabras genéricas
    {"fresa", "fresas", "turbina", "micromotor", "contraangulo"},

    # Brackets
    {"bracket", "brackets", "ortodoncia"},
    {"arco", "alambre", "arco orto"},

    # Adhesivos
    {"adhesivo", "bond", "primer", "bonding"},

    # Cementos
    {"cemento", "ionomero"},

    # Blanqueamiento
    {"blanqueamiento", "blanqueador", "whitening", "peroxido"},

    # Impresión
    {"impresion", "alginato", "vinilpolisiloxano", "putty"},

    # Guantes
    {"guante", "guantes"},

    # Radiografía
    {"radiografia", "rx", "pelicula", "placa radiografica"},

    # Postes
    {"poste", "perno", "fibra de vidrio"},

    # Sellantes
    {"sellante", "sellador", "fisuras"},

    # Yeso
    {"yeso", "escayola", "piedra dental"},

    # Prótesis
    {"protesis", "acrilico", "dentadura"},

    # Irrigantes
    {"hipoclorito", "irrigante", "edta", "irrigacion"},

    # Cirugía
    {"cirugia", "bisturi", "suturas", "periodoncia"},

    # Implantes
    {"implante", "implantologia", "pilar", "tornillo"},
]

def _norm_sin(s: str) -> str:
    """Normaliza un término para el mapa de sinónimos."""
    return normalizar(s)


if __name__ == "__main__":
    # Tests — verificar que la lógica es correcta
    tests = [
        # Composites
        ("Composite Filtek Z350 XT 3M A3 jeringa 4g",
         {"tipo": "composite", "marca": "3m", "tono": "a3"}),
        ("Composite Filtek P60 A3 x 4gr 3M",
         {"tipo": "composite", "marca": "3m", "linea": "p60"}),
        # Conos — distinción crítica
        ("Conos de Gutapercha Protaper Universal Dentsply",
         {"tipo": "cono_gutapercha", "marca": "dentsply"}),
        ("Cono de Papel ISO 15 Metabiomed x200",
         {"tipo": "cono_papel"}),
        ("Puntas de papel absorbentes #25",
         {"tipo": "cono_papel"}),  # NO debe dar cono_gutapercha
        # Limas — distinción crítica
        ("Lima K #25 25mm Dentsply",
         {"tipo": "lima", "subtipo": "manual_k"}),
        ("Lima H Hedstrom 25mm ISO 30",
         {"tipo": "lima", "subtipo": "manual_h"}),
        ("Lima WaveOne Gold Primary Dentsply",
         {"tipo": "lima", "subtipo": "reciprocante_waveone"}),
        ("Lima ProTaper Next X2 Dentsply",
         {"tipo": "lima", "subtipo": "rotatoria_protaper"}),
        # Anestesia
        ("Anestesia Anescart Forte x50",
         {"tipo": "anestesia", "droga": "anescart"}),
        ("Articaina 4% con epinefrina Septocaine x50",
         {"tipo": "anestesia", "droga": "articaina"}),
        ("Mepivacaina 3% sin vasoconstrictor x50",
         {"tipo": "anestesia", "droga": "mepivacaina"}),
        # Guantes
        ("Guantes nitrilo negros M x100",
         {"tipo": "guantes", "material": "nitrilo", "talle": "M"}),
    ]

    print("=== CATALOGADOR — TEST ===\n")
    errores = 0
    for nombre, esperado in tests:
        attrs = catalogar(nombre)
        ok = True
        for k, v in esperado.items():
            if attrs.get(k) != v:
                ok = False
                break
        status = "✅" if ok else "❌"
        print(f"{status} '{nombre}'")
        if not ok:
            errores += 1
            for k, v in esperado.items():
                got = attrs.get(k)
                marker = "  ✓" if got == v else "  ✗"
                print(f"{marker} {k}: esperado={v!r}, got={got!r}")
        else:
            print(f"   tipo={attrs.get('tipo')}, marca={attrs.get('marca')}, "
                  f"subtipo={attrs.get('subtipo')}, droga={attrs.get('droga')}")
        print()

    print(f"{'Todos los tests pasaron' if not errores else f'{errores} tests fallaron'}")
