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
#
# Estos no son reglas por producto — son vocabularios del dominio odontológico.
# Igual que un diccionario médico: los términos son fijos, las reglas son genéricas.

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
    "klepp", "delta", "metabiomed", "reciproc",
}

# Modelos con marca implícita — si aparece el modelo, se infiere la marca
# No existe P60 de otra marca que no sea 3M, etc.
_MODELO_MARCA = {
    # 3M / Solventum
    "p60": "3m", "z350": "3m", "z250": "3m", "z100": "3m",
    "filtek": "3m", "supreme": "3m", "silorane": "3m",
    "single bond": "3m", "scotchbond": "3m", "adper": "3m",
    "ketac": "3m", "relyx": "3m", "espe": "3m",
    # Ivoclar
    "tetric": "ivoclar", "empress": "ivoclar", "ips": "ivoclar",
    "vivadent": "ivoclar", "multilink": "ivoclar", "variolink": "ivoclar",
    "optibond": "ivoclar",
    # Dentsply / Maillefer
    "protaper": "dentsply", "waveone": "dentsply", "reciproc": "dentsply",
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

# Tipos de producto — palabras genéricas que identifican la categoría
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
    "punta": "fresa",
    "lima": "lima",
    "instrumento": "lima",
    "guante": "guantes",
    "guantes": "guantes",
    "adhesivo": "adhesivo",
    "bond": "adhesivo",
    "primer": "adhesivo",
    "cemento": "cemento",
    "ionomero": "cemento",
    "ionómero": "cemento",
    "gutapercha": "gutapercha",
    "guta": "gutapercha",
    "cono": "gutapercha",
    "conos": "gutapercha",
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
    "jeringa": "jeringa",
    "cubeta": "cubeta",
    "disco": "disco",
    "tira": "tira",
}

# Drogas anestésicas (pares que NO son intercambiables)
_DROGAS = {
    "mepivacaina", "lidocaina", "articaina", "bupivacaina", "prilocaina",
    "carticaina", "scandicaine", "alphacaine", "mepinor", "anescart",
    "ultracaine", "septocaine", "xylestesin", "citoject",
}

# Materiales (pares que NO son intercambiables)
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

# Subtipos funcionales de composite
_SUBTIPOS_COMPOSITE = {
    "flow": "flow",
    "flowable": "flow",
    "bulk": "bulk",
    "posterior": "posterior",
    "anteriores": "anterior",
    "universal": "universal",
    "esmalte": "esmalte",
    "enamel": "esmalte",
    "dentin": "dentina",
    "dentina": "dentina",
    "opaque": "opaco",
    "opaco": "opaco",
}

# Tokens que son SIEMPRE genéricos (nunca específicos)
_TOKENS_GENERICOS = {
    "composite", "resina", "anestesia", "guante", "guantes",
    "lima", "fresa", "adhesivo", "cemento", "yeso", "cono", "conos",
    "poste", "bracket", "disco", "tira", "jeringa", "carpule",
    "aguja", "agujas", "cubeta", "alginato", "silicona",
    "blanqueador", "sellante", "hipoclorito", "irrigante",
    "instrumental", "material", "producto", "insumo",
    "dental", "odontologico", "odontológico",
    "para", "sin", "con", "tipo", "uso", "x",
}


# ─── CATALOGADOR ──────────────────────────────────────────────────────────────

def catalogar(nombre_crudo: str) -> dict:
    """
    Extrae atributos estructurados de un nombre de producto odontológico.
    Devuelve dict con los atributos encontrados (None si no detecta).
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

    # ── TIPO ──
    for palabra, tipo in _TIPOS.items():
        if re.search(r"\b" + re.escape(palabra) + r"\b", t):
            attrs["tipo"] = tipo
            break

    # ── MARCA ──
    for marca in sorted(_MARCAS, key=len, reverse=True):  # más largas primero
        if re.search(r"\b" + re.escape(marca) + r"\b", t):
            attrs["marca"] = marca
            break
    # Si no detectó marca, inferir desde modelo/línea conocida
    # NO inferir si el producto dice "simil", "similar", "tipo", "estilo" — son copias
    _es_copia = bool(re.search(r"\b(simil|similar|tipo|estilo|alternativ|generico|equivalente|reforzado para)\b", t))
    if not attrs.get("marca") and not _es_copia:
        for modelo_key, marca_implicita in _MODELO_MARCA.items():
            if re.search(r"\b" + re.escape(modelo_key) + r"\b", t):
                attrs["marca"] = marca_implicita
                break

    # ── LÍNEA COMERCIAL (Filtek, Tetric, ProTaper, etc.) ──
    # Detectar palabras con mayúscula inicial que no son tipo/marca ya detectada
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
    for linea in sorted(lineas_conocidas, key=len, reverse=True):
        if re.search(r"\b" + re.escape(linea) + r"\b", t):
            attrs["linea"] = linea
            break

    # ── MODELO alfanumérico (z350xt, p60, z250, etc.) ──
    modelos = re.findall(r"\b([a-z]{1,5}[0-9]{2,4}[a-z]{0,4})\b", t)
    modelos = [m for m in modelos
               if len(m) >= 3
               and not re.match(r"^(iso|pro|con|mas|x\d+|nro|num)$", m)
               and not m.isdigit()]
    if modelos:
        attrs["modelo"] = modelos[0]

    # ── SUBTIPO (flow, bulk, esmalte, dentina, etc.) ──
    for palabra, subtipo in _SUBTIPOS_COMPOSITE.items():
        if re.search(r"\b" + re.escape(palabra) + r"\b", t):
            attrs["subtipo"] = subtipo
            break

    # ── TONO dental (A1, A2, A3, B1, C2, D3, A3.5) ──
    tonos = re.findall(r"\b([a-d][0-9](?:[.,][0-9])?)\b", t)
    if tonos:
        attrs["tono"] = tonos[0]

    # ── MATERIAL ──
    for mat in _MATERIALES:
        if re.search(r"\b" + mat[:5] + r"\w*\b", t):
            attrs["material"] = mat
            break

    # ── COLOR ──
    for col in _COLORES:
        if re.search(r"\b" + col[:4] + r"\w*\b", t):
            attrs["color"] = col
            break

    # ── DROGA ANESTÉSICA ──
    for droga in _DROGAS:
        if re.search(r"\b" + droga[:6] + r"\w*\b", t):
            attrs["droga"] = droga
            break

    # ── TALLE ──
    talle = re.search(r"\b(?:talle\s*|talla\s*|size\s*)?([xX]{0,2}[sSlLmM])\b(?!\w)", t)
    if talle:
        attrs["talle"] = talle.group(1).upper()

    # ── CALIBRE de instrumento (# 25, ISO 25, nro 15) ──
    calib = re.search(r"#\s*(\d{1,3})\b", orig)
    if not calib:
        calib = re.search(r"\biso\s*(\d{1,3})\b", t)
    if not calib:
        calib = re.search(r"\bnro?\.?\s*(\d{1,3})\b", t)
    if calib:
        attrs["calibre"] = calib.group(1)

    # ── LONGITUD ──
    long_m = re.search(r"\b(\d+)\s*mm\b", t)
    if long_m:
        attrs["longitud"] = long_m.group(1) + "mm"

    # ── PESO ──
    peso_m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(g|gr|kg|ml)\b", t)
    if peso_m:
        attrs["peso"] = peso_m.group(1) + peso_m.group(2)

    # ── CANTIDAD ──
    cant = re.search(r"\bx\s*(\d+)\b", t)
    if not cant:
        cant = re.search(r"\b(\d+)\s*(?:unidades|unid|u\b|caps?|carpules?)", t)
    if cant:
        attrs["cantidad"] = int(cant.group(1))

    # ── PRESENTACIÓN ──
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

    Tokens específicos = marcas, modelos, códigos, tonos, calibres, drogas, etc.
    Tokens genéricos = tipo de producto, palabras descriptivas

    Retorna:
        {
            "especificos": ["anescart", "forte"],
            "genericos": ["anestesia"],
            "todos": ["anestesia", "anescart", "forte"]
        }
    """
    t = normalizar(query)
    tokens_raw = [tok for tok in t.split() if len(tok) > 1]

    especificos = []
    genericos = []

    for tok in tokens_raw:
        # Es específico si:
        # - Es una marca conocida
        # - Es un modelo alfanumérico (z350, p60, a3, #25)
        # - Es una droga anestésica
        # - Tiene números (medidas, calibres)
        # - Es de longitud >= 5 y no está en genéricos

        es_marca = tok in _MARCAS
        es_droga = tok in _DROGAS
        tiene_numero = bool(re.search(r"[0-9]", tok))
        es_generico = tok in _TOKENS_GENERICOS
        es_tono = bool(re.match(r"^[a-d][0-9]$", tok))
        es_largo = len(tok) >= 5 and not es_generico

        if es_marca or es_droga or tiene_numero or es_tono or (es_largo and not es_generico):
            especificos.append(tok)
        else:
            genericos.append(tok)

    return {
        "especificos": especificos,
        "genericos": genericos,
        "todos": tokens_raw,
    }



# ─── SINÓNIMOS (exportados para uso en app.py) ────────────────────────────────
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
    {"hipoclorito","irrigante","edta","irrigacion"},
    {"cirugia","bisturi","suturas","periodoncia"},
    {"implante","implantologia","pilar","tornillo"},
]

def _norm_sin(s: str) -> str:
    """Normaliza un término para el mapa de sinónimos."""
    return normalizar(s)


if __name__ == "__main__":
    # Tests rápidos
    tests = [
        "Composite Filtek Z350 XT 3M A3 jeringa 4g",
        "Anestesia Anescart Forte x50",
        "Guantes nitrilo negros M x100",
        "Lima K #25 25mm Dentsply",
        "Adhesivo 3M Single Bond Universal 8ml",
        "Composite Filtek P60 A3 x 4gr 3M",
        "Fresa redonda larga FG carbide",
        "Conos de papel ISO 15-40 Metabiomed",
        "Hipoclorito de Sodio 5.25% 1 litro",
        "Bracket Metalico Roth 0.22 American Orthodontics",
    ]
    print("=== CATALOGADOR — TEST ===\n")
    for nombre in tests:
        attrs = catalogar(nombre)
        print(f"'{nombre}'")
        for k, v in attrs.items():
            print(f"  {k}: {v}")
        print()
