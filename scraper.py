"""
scraper.py - OdontoPrecio — Comparador de insumos odontológicos Argentina
"""

try:
    from curl_cffi import requests
    USE_CURL = True
except ImportError:
    import requests
    USE_CURL = False

from bs4 import BeautifulSoup
import json, os, time, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── TIENDAS ──────────────────────────────────────────────────────────────────
TIENDAS = [
    # ── TIENDANUBE ──
    {"slug":"dentaltronador","nombre":"Dental Tronador","url_base":"https://www.dentaltronador.com.ar","tipo":"tiendanube","sitemap":"https://www.dentaltronador.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#e63946"},
    {"slug":"iow","nombre":"IOW Insumos","url_base":"https://www.insumosodontologicosweb.com.ar","tipo":"tiendanube","sitemap":"https://www.insumosodontologicosweb.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#0284c7"},
    {"slug":"tedo","nombre":"Tedo Odontologia","url_base":"https://www.tedodontologia.com","tipo":"tiendanube","sitemap":"https://www.tedodontologia.com/sitemap.xml","filtro_sitemap":"/productos/","color":"#0d9488"},
    {"slug":"olympic","nombre":"Olympic Dental","url_base":"https://olympicdental.com","tipo":"tiendanube","sitemap":"https://olympicdental.com/sitemap.xml","filtro_sitemap":"/productos/","color":"#7c3aed"},
    {"slug":"dentalpunilla","nombre":"Dental Punilla","url_base":"https://www.dentalpunilla.com.ar","tipo":"tiendanube","sitemap":"https://www.dentalpunilla.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#16a34a"},
    {"slug":"grossdental","nombre":"Gross Dental","url_base":"https://www.grossdental.net","tipo":"tiendanube","sitemap":"https://www.grossdental.net/sitemap.xml","filtro_sitemap":"/productos/","color":"#ea580c"},
    {"slug":"renedental","nombre":"Rene Dental","url_base":"https://renedental.com.ar","tipo":"tiendanube","sitemap":"https://renedental.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#be185d"},
    {"slug":"dentalpack","nombre":"Dental Pack","url_base":"https://www.dentalpack.com.ar","tipo":"tiendanube","sitemap":"https://www.dentalpack.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#475569"},
    {"slug":"prodent","nombre":"Prodent","url_base":"https://www.prodent.com.ar","tipo":"tiendanube","sitemap":"https://www.prodent.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#b45309"},
    {"slug":"odentia","nombre":"Odentia","url_base":"https://www.odentia.com.ar","tipo":"tiendanube","sitemap":"https://www.odentia.com.ar/sitemap.xml","filtro_sitemap":"/productos/","color":"#0284c7"},
    {"slug":"dentalsupply","nombre":"Dental Supply","url_base":"https://dentalsupply.mitiendanube.com","tipo":"tiendanube","sitemap":"https://dentalsupply.mitiendanube.com/sitemap.xml","filtro_sitemap":"/productos/","color":"#16a34a"},
    # ── WOOCOMMERCE CON SITEMAP ──
    {"slug":"grimberg","nombre":"Grimberg Dentales","url_base":"https://grimbergdentales.com","tipo":"woocommerce","sitemap":"https://grimbergdentales.com/product-sitemap.xml","filtro_sitemap":"/producto/","color":"#2a9d8f"},
    {"slug":"dentalshop","nombre":"Dental Shop","url_base":"https://dentalshop.com.ar","tipo":"woocommerce","sitemap":"https://dentalshop.com.ar/wp-sitemap-posts-product-1.xml","filtro_sitemap":"/product/","color":"#e63946"},
    {"slug":"dento","nombre":"Dento","url_base":"https://dento.com.ar","tipo":"woocommerce","sitemap":"https://dento.com.ar/wp-sitemap-posts-product-1.xml","filtro_sitemap":"/product/","color":"#7c3aed"},
    {"slug":"dentalmedrano","nombre":"Dental Medrano","url_base":"https://dentalmedrano.com","tipo":"woocommerce","sitemap":"https://dentalmedrano.com/product-sitemap.xml","filtro_sitemap":"/producto/","color":"#ea580c","sitemap_extra":"https://dentalmedrano.com/product-sitemap2.xml"},
    {"slug":"dentalstorearg","nombre":"Dental Store Argentina","url_base":"https://dentalstoreargentina.com","tipo":"woocommerce","sitemap":"https://dentalstoreargentina.com/wp-sitemap-posts-product-1.xml","filtro_sitemap":"/producto/","color":"#0d9488"},
    {"slug":"axdental","nombre":"Axdental","url_base":"https://axdental.com.ar","tipo":"woocommerce","sitemap":"https://axdental.com.ar/product-sitemap.xml","filtro_sitemap":"/productos/","color":"#be185d"},
    {"slug":"bairesdental","nombre":"Baires Dental","url_base":"https://bairesdental.com.ar","tipo":"woocommerce","sitemap":"https://bairesdental.com.ar/wp-sitemap-posts-product-1.xml","filtro_sitemap":"/producto/","color":"#475569"},
    # Occidental Dental: requiere login para ver precios — no scrapeable
    # {"slug":"occidental","nombre":"Occidental Dental",...},
    {"slug":"odontomed","nombre":"Odontomed Insumos","url_base":"https://odontomedinsumos.com","tipo":"woocommerce","sitemap":"https://odontomedinsumos.com/product-sitemap.xml","filtro_sitemap":"/producto/","color":"#b45309"},
    # ── PRESTASHOP ──
    {
        "slug":"mauri","nombre":"Odontologia Mauri","url_base":"https://odontologiamauri.com.ar",
        "tipo":"prestashop","sitemap":None,"color":"#be185d",
        "categorias":["30-instrumental","31-operatoria","32-equipamiento","33-estetica","35-protesis","36-endodoncia","37-ortodoncia","38-cirugia","39-periodoncia","40-rayos","41-laboratorio","42-odontopediatria"],
    },
    # ── WOOCOMMERCE PAGINADO ──
    {"slug":"orthodent","nombre":"Orthodent","url_base":"https://www.orthodent.com.ar","tipo":"woocommerce_paginado","sitemap":None,"url_productos":"https://www.orthodent.com.ar/todos-los-productos/","color":"#457b9d"},
    # ── CARRIZO DENTAL (PHP propio por categorias) ──
    {
        "slug":"carrizo","nombre":"Carrizo Dental","url_base":"https://carrizodental.com",
        "tipo":"carrizo","sitemap":None,"color":"#dc2626",
        "categorias_ids":[1,7,23,34,41,44,46,49,52,62,66,102,112,162,198],
    },
    # ── DENTALAB (Joomla por categorias) ──
    {
        "slug":"dentalab","nombre":"Dentalab","url_base":"https://dentalab.com.ar",
        "tipo":"dentalab","sitemap":None,"color":"#0369a1",
        "categorias_urls":[
            "/productos/anestesias.html",
            "/productos/composites-y-compomeros.html",
            "/productos/adhesivos.html",
            "/productos/cementos.html",
            "/productos/endodoncia.html",
            "/productos/ortodoncia.html",
            "/productos/cirugia.html",
            "/productos/periodoncia.html",
            "/productos/blanqueamiento.html",
            "/productos/bioseguridad.html",
            "/productos/instrumental.html",
            "/productos/radiologia.html",
            "/productos/laboratorio.html",
            "/productos/protesis.html",
            "/productos/acrilicos-y-rebasado.html",
            "/productos/yesos-y-revestimientos.html",
            "/productos/materiales-de-impresion.html",
            "/productos/equipamiento.html",
            "/productos/descartables.html",
        ],
    },
    # ── ODONTOSTORE (Custom por categorias) ──
    {
        "slug":"odontostore","nombre":"Odontostore","url_base":"https://www.odontostore.com",
        "tipo":"odontostore","sitemap":None,"color":"#16a34a",
        "categorias_urls":[
            "/es/productos/descartables/agujas",
            "/es/productos/descartables/barbijos",
            "/es/productos/descartables/baberos",
            "/es/productos/descartables/compresas",
            "/es/productos/descartables/canulas",
            "/es/productos/descartables/eyectores",
            "/es/productos/descartables/gasas",
            "/es/productos/descartables/guantes",
            "/es/productos/descartables/hojas-de-bisturi",
            "/es/productos/anestesia",
            "/es/productos/composite",
            "/es/productos/adhesivos",
            "/es/productos/cementos",
            "/es/productos/endodoncia",
            "/es/productos/ortodoncia",
            "/es/productos/cirugia",
            "/es/productos/blanqueamiento",
            "/es/productos/instrumental",
            "/es/productos/radiologia",
            "/es/productos/equipamiento",
            "/es/productos/laboratorio",
            "/es/productos/impresion",
            "/es/productos/protesis",
        ],
    },
    # ── CEDENT (Custom por categorias) ──
    {
        "slug":"cedent","nombre":"Cedent","url_base":"https://www.cedent.com.ar",
        "tipo":"cedent","sitemap":None,"color":"#7c3aed",
        "categorias_urls":[
            "/shop/category/operatoria-y-restauracion-adhesivos-168",
            "/shop/category/anestesias-y-agujas-53",
            "/shop/category/bioseguridad-402",
            "/shop/category/estetica-blanqueamiento-54",
            "/shop/category/cementos-55",
            "/shop/category/cirugia-y-perio-56",
            "/shop/category/operatoria-y-restauracion-composites-171",
            "/shop/category/descartables-57",
            "/shop/category/endodoncia-58",
            "/shop/category/equipamiento-59",
            "/shop/category/instrumental-60",
            "/shop/category/laboratorio-61",
            "/shop/category/materiales-de-impresion-62",
            "/shop/category/ortodoncia-63",
            "/shop/category/protesis-64",
            "/shop/category/radiologia-65",
            "/shop/category/yesos-66",
        ],
    },
]

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "productos.json")
MAX_WORKERS = 5
DELAY = 0.3

# ─── HTTP ─────────────────────────────────────────────────────────────────────
def fetch(url, timeout=20, reintentos=2):
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    ultimo_error = None
    for intento in range(reintentos + 1):
        try:
            if USE_CURL:
                return requests.get(url, impersonate="chrome124", timeout=timeout)
            return requests.get(url, headers=hdrs, timeout=timeout)
        except Exception as e:
            ultimo_error = e
            if intento < reintentos:
                time.sleep(1)
    raise ultimo_error

# ─── UTILS ────────────────────────────────────────────────────────────────────
def limpiar_precio(texto):
    if not texto: return 0.0
    txt = re.sub(r"[^\d,.]", "", str(texto))
    if not txt: return 0.0
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "." in txt:
        if len(txt.split(".")[-1]) == 3:
            txt = txt.replace(".", "")
    elif "," in txt:
        if len(txt.split(",")[-1]) == 3:
            txt = txt.replace(",", "")
        else:
            txt = txt.replace(",", ".")
    try:
        v = float(txt)
        return v if 0 < v < 99_000_000 else 0.0
    except ValueError:
        return 0.0

def formatear_precio(precio):
    if not precio or precio <= 0: return "Consultar"
    return "$" + f"{precio:,.0f}".replace(",", ".")

def hacer_producto(tienda, nombre, precio, url_prod, imagen):
    return {
        "id": f"{tienda['slug']}_{abs(hash(url_prod))}",
        "nombre": nombre.strip()[:200],
        "precio": precio,
        "precio_fmt": formatear_precio(precio),
        "url": url_prod,
        "imagen": imagen or "",
        "tienda_slug": tienda["slug"],
        "tienda_nombre": tienda["nombre"],
        "tienda_color": tienda["color"],
        "actualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

# ─── SITEMAP ──────────────────────────────────────────────────────────────────
def obtener_urls_sitemap(sitemap_url, filtro):
    try:
        r = fetch(sitemap_url, timeout=20)
        if r.status_code != 200: return []
        for parser in ["xml", "html.parser"]:
            soup = BeautifulSoup(r.text, parser)
            locs = [l.text for l in soup.find_all("loc")]
            if locs: break
        if not locs:
            locs = re.findall(r'<loc>(https?://[^<]+)</loc>', r.text)
        EXCLUIR = ["/categoria-producto/", "/product-category/", "/tag/", "/categoria/"]
        urls = [u for u in locs if filtro in u and not any(x in u for x in EXCLUIR)]
        return urls
    except Exception as e:
        print(f"  ! Sitemap error: {e}")
        return []

# ─── SCRAPING TIENDANUBE ──────────────────────────────────────────────────────
def scrape_producto_tiendanube(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "html.parser")
        sin_stock = soup.select_one(".js-buy-button[disabled], .buy-button[disabled]")
        if sin_stock: return None
        nombre_el = soup.select_one(".js-item-name, .product-name, h1.product-name, h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        if not nombre: return None
        precio_el = soup.select_one(".js-price-display, .product-price.js-price-display, h2.js-price-display") or soup.select_one("[class*='price']")
        precio_txt = precio_el.get_text(strip=True) if precio_el else ""
        precios = re.findall(r"\$[\d.,]+", precio_txt)
        precio = limpiar_precio(precios[0] if precios else precio_txt)
        if not precio: return None
        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""
        return hacer_producto(tienda, nombre, precio, url, imagen)
    except Exception:
        return None

# ─── SCRAPING WOOCOMMERCE ─────────────────────────────────────────────────────
def scrape_producto_woocommerce(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "html.parser")
        if soup.select_one(".out-of-stock, p.stock.out-of-stock"): return None
        # Primero intentar variaciones de producto (WooCommerce variable product)
        form_var = soup.select_one("form.variations_form[data-product_variations]")
        if form_var:
            try:
                variations = json.loads(form_var.get("data-product_variations", "[]"))
                if variations:
                    # Tomar el precio minimo real (excluir precios 0)
                    precios_vars = [v.get("display_price", 0) for v in variations if v.get("display_price", 0) > 50]
                    if precios_vars:
                        precio = min(precios_vars)
                        nombre_el = soup.select_one("h1.product_title, h1.entry-title, h1")
                        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
                        img_el = soup.select_one('meta[property="og:image"]')
                        imagen = img_el["content"] if img_el else ""
                        if nombre:
                            return hacer_producto(tienda, nombre, precio, url, imagen)
            except Exception:
                pass

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = next((d for d in data if d.get("@type") == "Product"), None)
                if data and data.get("@type") == "Product":
                    if "OutOfStock" in data.get("offers", {}).get("availability", ""): return None
                    nombre = data.get("name", "")
                    # Manejar offerS multiple (AggregateOffer)
                    offers = data.get("offers", {})
                    if offers.get("@type") == "AggregateOffer":
                        precio = limpiar_precio(str(offers.get("lowPrice", offers.get("price", 0))))
                    else:
                        precio = limpiar_precio(str(offers.get("price", 0)))
                    imagen = data.get("image", "")
                    if isinstance(imagen, list): imagen = imagen[0] if imagen else ""
                    if nombre and precio and precio > 50:
                        # Verificar si hay precio de oferta en HTML que sea menor (precio real)
                        precio_oferta_el = soup.select_one(".price ins .woocommerce-Price-amount, .price ins .amount")
                        if precio_oferta_el:
                            precio_oferta = limpiar_precio(precio_oferta_el.get_text(strip=True))
                            if precio_oferta and precio_oferta < precio:
                                precio = precio_oferta
                        return hacer_producto(tienda, nombre, precio, url, imagen)
            except Exception:
                continue
        nombre_el = soup.select_one("h1.product_title, h1.entry-title, h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        # Priorizar precio de oferta (ins) sobre precio normal
        # Esto evita tomar el precio tachado cuando hay descuento
        precio_oferta = soup.select_one(".price ins .woocommerce-Price-amount, .price ins .amount")
        precio_normal = soup.select_one(".price .woocommerce-Price-amount, .price .amount, [itemprop='price']")
        precio_el = precio_oferta or precio_normal
        precio_txt = (precio_el.get("content") or precio_el.get_text(strip=True)) if precio_el else ""
        precio = limpiar_precio(precio_txt)
        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""
        if nombre and precio:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None
    except Exception:
        return None

# ─── SCRAPING PRESTASHOP ──────────────────────────────────────────────────────
def scrape_producto_prestashop(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "html.parser")
        avail_el = soup.select_one(".js-product-availability, #product-availability")
        if avail_el and any(w in avail_el.get_text().lower() for w in ["fuera de stock", "sin stock", "agotado"]): return None
        nombre_el = soup.select_one("h1.product-detail-name, h1[itemprop='name'], h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        precio_el = soup.select_one("[itemprop='price'], .current-price span, .product-price")
        precio_txt = (precio_el.get("content") or precio_el.get_text(strip=True)) if precio_el else ""
        precio = limpiar_precio(precio_txt)
        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""
        if nombre and precio:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None
    except Exception:
        return None

# ─── MOTOR CON SITEMAP ────────────────────────────────────────────────────────
def scrape_con_sitemap(tienda):
    print(f"  Leyendo sitemap...")
    urls = obtener_urls_sitemap(tienda["sitemap"], tienda["filtro_sitemap"])
    if tienda.get("sitemap_extra"):
        urls += obtener_urls_sitemap(tienda["sitemap_extra"], tienda["filtro_sitemap"])
    urls = list(set(urls))
    print(f"  {len(urls)} URLs — scrapeando...")
    if not urls: return []
    fn = scrape_producto_tiendanube if tienda["tipo"] == "tiendanube" else scrape_producto_woocommerce
    productos, errores, total = [], 0, len(urls)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fn, url, tienda): url for url in urls}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            if r: productos.append(r)
            else: errores += 1
            if i % 100 == 0 or i == total:
                print(f"  [{i}/{total}] {len(productos)} OK, {errores} sin precio/stock")
            time.sleep(DELAY / MAX_WORKERS)
    return productos

# ─── MOTOR PAGINADO WOOCOMMERCE ───────────────────────────────────────────────
def scrape_paginado_woocommerce(tienda):
    productos, page = [], 1
    url_base = tienda.get("url_productos", f"{tienda['url_base']}/shop/")
    while True:
        url = url_base if page == 1 else f"{url_base.rstrip('/')}/page/{page}/"
        try:
            r = fetch(url, timeout=15)
            if r.status_code != 200: break
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("li.product, article.product")
            if not items: break
            urls_pagina = []
            for item in items:
                link = item.select_one("a.woocommerce-LoopProduct-link, h2 a, h3 a, a[href]")
                if link:
                    href = link["href"]
                    if not any(x in href for x in ["/categoria-producto/", "/product-category/"]): urls_pagina.append(href)
            print(f"  Pag {page}: {len(urls_pagina)} productos")
            for url_prod in urls_pagina:
                prod = scrape_producto_woocommerce(url_prod, tienda)
                if prod: productos.append(prod)
                time.sleep(DELAY)
            if not soup.select_one("a.next, .next.page-numbers, a[rel='next']"): break
            page += 1
        except Exception as e:
            print(f"  ! Pag {page}: {e}")
            break
    return productos

# ─── MOTOR PRESTASHOP CATEGORIAS ─────────────────────────────────────────────
def scrape_categorias_prestashop(tienda):
    productos, ids_vistos = [], set()
    for cat in tienda.get("categorias", []):
        cat_url = f"{tienda['url_base']}/{cat}"
        page = 1
        print(f"  Cat: {cat}")
        while True:
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            try:
                r = fetch(url, timeout=15)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select(".js-product, article.product-miniature")
                if not items: break
                for item in items:
                    link = item.select_one("a[href]")
                    if not link: continue
                    url_prod = link["href"]
                    if url_prod in ids_vistos: continue
                    ids_vistos.add(url_prod)
                    prod = scrape_producto_prestashop(url_prod, tienda)
                    if prod: productos.append(prod)
                    time.sleep(DELAY)
                if not soup.select_one("a[rel='next'], li.next a"): break
                page += 1
            except Exception as e:
                print(f"  ! {e}")
                break
    return productos

# ─── MOTOR CARRIZO ────────────────────────────────────────────────────────────
def scrape_carrizo(tienda):
    """PHP propio. Categorias via ?agru_1=ID, productos via /articulo.php?cod_articulo=COD"""
    productos, urls_vistas = [], set()
    for cat_id in tienda.get("categorias_ids", []):
        cat_url = f"{tienda['url_base']}/index.php?agru_1={cat_id}"
        print(f"  Cat agru_1={cat_id}")
        try:
            r = fetch(cat_url, timeout=15)
            if r.status_code != 200: continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Links a productos individuales
            prod_links = soup.select("a[href*='cod_articulo']")
            urls_cat = []
            for link in prod_links:
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = tienda["url_base"] + "/" + href.lstrip("/")
                if href not in urls_vistas:
                    urls_vistas.add(href)
                    urls_cat.append(href)
            print(f"    {len(urls_cat)} productos")
            for url_prod in urls_cat:
                prod = _scrape_producto_carrizo(url_prod, tienda)
                if prod: productos.append(prod)
                time.sleep(DELAY)
        except Exception as e:
            print(f"  ! Cat {cat_id}: {e}")
    return productos

def _scrape_producto_carrizo(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Nombre: h1 o titulo del producto
        nombre_el = soup.select_one("h1, .producto-nombre, .nombre-articulo, [class*='titulo']")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        if not nombre:
            # Intentar og:title
            og = soup.select_one('meta[property="og:title"]')
            nombre = og["content"] if og else ""
        # Precio: buscar patron $XX.XXX
        precio_el = soup.select_one("[class*='precio'], [class*='price'], .precio-articulo")
        precio_txt = precio_el.get_text(strip=True) if precio_el else ""
        if not precio_txt:
            # Buscar en todo el texto
            match = re.search(r'\$\s*[\d.,]+', soup.get_text())
            precio_txt = match.group(0) if match else ""
        precio = limpiar_precio(precio_txt)
        img_el = soup.select_one('meta[property="og:image"]') or soup.select_one("img[src*='/img/articulos/']")
        imagen = (img_el.get("content") or img_el.get("src", "")) if img_el else ""
        if imagen and not imagen.startswith("http"):
            imagen = tienda["url_base"] + "/" + imagen.lstrip("/")
        if nombre and precio:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None
    except Exception:
        return None

# ─── MOTOR DENTALAB ───────────────────────────────────────────────────────────
def scrape_dentalab(tienda):
    """Joomla/VirtueMart. Listings por categoria, productos con URLs /productos/cat/nombre.html"""
    productos, urls_vistas = [], set()
    for cat_path in tienda.get("categorias_urls", []):
        cat_url = tienda["url_base"] + cat_path
        # Extraer nombre de categoria para buscar links
        cat_nombre = cat_path.strip("/").split("/")[-1].replace(".html", "")
        page = 0
        print(f"  Cat: {cat_nombre}")
        while True:
            url = f"{cat_url}?start={page*20}" if page > 0 else cat_url
            try:
                r = fetch(url, timeout=15)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "html.parser")

                # Links a productos individuales (tienen /productos/categoria/nombre.html)
                prod_links = soup.select(f"a[href*='/productos/{cat_nombre}/']")
                prod_links = [a for a in prod_links 
                             if a.get("href","").endswith(".html") 
                             and not any(x in a.get("href","") for x in ["dirDesc","por,","ordenar"])]

                if not prod_links and page > 0: break
                if not prod_links: break

                encontro_nuevos = False
                for a in prod_links:
                    href = a.get("href", "")
                    if not href.startswith("http"): href = tienda["url_base"] + href
                    if href in urls_vistas: continue
                    urls_vistas.add(href)
                    prod = _scrape_producto_dentalab(href, tienda)
                    if prod:
                        productos.append(prod)
                        encontro_nuevos = True
                    time.sleep(DELAY)

                if not encontro_nuevos: break
                # Verificar paginacion
                next_btn = soup.select_one("a[href*='start=']")
                if not next_btn: break
                page += 1
            except Exception as e:
                print(f"  ! {e}")
                break
    return productos

def _scrape_producto_dentalab(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200: return None
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Nombre: h1 o og:title
        nombre_el = soup.select_one("h1, .product-title, [itemprop='name']")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        if not nombre:
            og = soup.select_one('meta[property="og:title"]')
            nombre = og["content"] if og else ""
        
        # Precio: VirtueMart usa .PriceproductPrice o itemprop=price
        precio_el = soup.select_one("[itemprop='price'], .PriceproductPrice, .product-price, .productPrice")
        precio_txt = ""
        if precio_el:
            precio_txt = precio_el.get("content") or precio_el.get_text(strip=True)
        if not precio_txt:
            # Buscar en el texto del body
            match = re.search(r'\$\s*[\d.,]+', soup.get_text())
            precio_txt = match.group(0) if match else ""
        precio = limpiar_precio(precio_txt)
        
        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""
        
        if nombre and precio and precio > 50:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None
    except Exception:
        return None

# ─── MOTOR ODONTOSTORE ────────────────────────────────────────────────────────
def scrape_odontostore(tienda):
    """Custom PHP. Los productos se muestran directamente en la pagina de categoria."""
    productos, urls_vistas = [], set()
    for cat_path in tienda.get("categorias_urls", []):
        cat_url = tienda["url_base"] + cat_path
        page = 1
        print(f"  Cat: {cat_path.split('/')[-1]}")
        while True:
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            try:
                r = fetch(url, timeout=15)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "html.parser")
                # Buscar productos en la pagina - tienen nombre, precio y link
                items = soup.select("[class*='product'], [class*='item-prod'], .card")
                if not items and page > 1: break
                encontro_nuevos = False
                for item in items:
                    nombre_el = item.select_one("[class*='name'], [class*='title'], h2, h3, h4")
                    precio_el = item.select_one("[class*='price'], [class*='precio']")
                    link_el = item.select_one("a[href*='/es/productos/']")
                    if not nombre_el or not precio_el: continue
                    nombre = nombre_el.get_text(strip=True)
                    precio = limpiar_precio(precio_el.get_text(strip=True))
                    href = link_el.get("href", "") if link_el else cat_url
                    if not href.startswith("http"): href = tienda["url_base"] + href
                    if href in urls_vistas: continue
                    urls_vistas.add(href)
                    encontro_nuevos = True
                    img_el = item.select_one("img")
                    imagen = img_el.get("src", "") if img_el else ""
                    if imagen and not imagen.startswith("http"): imagen = tienda["url_base"] + imagen
                    if nombre and precio:
                        productos.append(hacer_producto(tienda, nombre, precio, href, imagen))
                if not encontro_nuevos: break
                if not soup.select_one("a[rel='next'], .next, a[href*='page=']"): break
                page += 1
            except Exception as e:
                print(f"  ! {e}")
                break
    return productos

# ─── MOTOR CEDENT ─────────────────────────────────────────────────────────────
def scrape_cedent(tienda):
    """Odoo. Listing de categoria con productos y precios directamente en la pagina."""
    productos, urls_vistas = [], set()
    for cat_path in tienda.get("categorias_urls", []):
        cat_url = tienda["url_base"] + cat_path
        page = 1
        cat_id = cat_path.split("-")[-1]  # Extraer ID de la URL
        print(f"  Cat: {cat_path.split('/')[-1][:30]}")
        while True:
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            try:
                r = fetch(url, timeout=15)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "html.parser")

                # Odoo: productos en cards con link al producto y precio en .oe_currency_value
                # Buscar todos los links a productos (no categorias, no cart)
                EXCLUIR = ["/category/", "/cart", "/wishlist", "change_pricelist", "/product/"]
                prod_anchors = soup.select("a[href*='/shop/']")
                
                encontro_nuevos = False
                prods_pagina = []
                for a in prod_anchors:
                    href = a.get("href", "")
                    if any(x in href for x in EXCLUIR): continue
                    if not href.startswith("http"): href = tienda["url_base"] + href
                    # Limpiar parametros ?category=
                    href_limpia = href.split("?")[0]
                    if href_limpia in urls_vistas: continue
                    prods_pagina.append((href_limpia, a))
                    urls_vistas.add(href_limpia)

                if not prods_pagina and page > 1: break

                # Para cada producto del listing, obtener nombre y precio desde la pagina individual
                for url_prod, _ in prods_pagina:
                    try:
                        rp = fetch(url_prod, timeout=15)
                        if rp.status_code != 200: continue
                        sp = BeautifulSoup(rp.text, "html.parser")
                        
                        nombre_el = sp.select_one("h1[itemprop='name'], h1.product-name, h1")
                        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
                        
                        # Precio con itemprop=price (content tiene el valor numerico)
                        precio_el = sp.select_one("[itemprop='price']")
                        if precio_el:
                            precio = limpiar_precio(precio_el.get("content") or precio_el.get_text(strip=True))
                        else:
                            # Fallback: primer .oe_currency_value
                            cv = sp.select_one(".oe_currency_value")
                            precio = limpiar_precio(cv.get_text(strip=True)) if cv else 0

                        img_el = sp.select_one('meta[property="og:image"]')
                        imagen = img_el["content"] if img_el else ""

                        if nombre and precio and precio > 50:
                            productos.append(hacer_producto(tienda, nombre, precio, url_prod, imagen))
                            encontro_nuevos = True
                        time.sleep(DELAY)
                    except Exception:
                        continue

                if not encontro_nuevos and page > 1: break
                # Paginacion Odoo
                next_btn = soup.select_one("a.page-link[aria-label='Next'], .o_website_scrollup ~ * a[href*='page='], a[href*='page=']")
                if not next_btn: break
                page += 1
            except Exception as e:
                print(f"  ! {e}")
                break
    return productos

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def correr_scraper():
    todos = []
    inicio_total = time.time()
    for tienda in TIENDAS:
        inicio = time.time()
        print(f"\n{'='*50}\nScrapeando: {tienda['nombre']}\n{'='*50}")
        try:
            tipo = tienda["tipo"]
            if tipo in ("tiendanube", "woocommerce") and tienda.get("sitemap"):
                prods = scrape_con_sitemap(tienda)
            elif tipo == "woocommerce_paginado":
                prods = scrape_paginado_woocommerce(tienda)
            elif tipo == "prestashop":
                prods = scrape_categorias_prestashop(tienda)
            elif tipo == "carrizo":
                prods = scrape_carrizo(tienda)
            elif tipo == "dentalab":
                prods = scrape_dentalab(tienda)
            elif tipo == "odontostore":
                prods = scrape_odontostore(tienda)
            elif tipo == "cedent":
                prods = scrape_cedent(tienda)
            else:
                prods = []
        except Exception as e:
            print(f"  ERROR: {e}")
            prods = []
        print(f"  TOTAL: {len(prods)} productos en {int(time.time()-inicio)}s")
        todos.extend(prods)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*50}\nTERMINADO: {len(todos)} productos en {int(time.time()-inicio_total)}s\nGuardado en: {DB_PATH}\n{'='*50}")
    return todos

def cargar_productos():
    if not os.path.exists(DB_PATH):
        return correr_scraper()
    with open(DB_PATH, encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    correr_scraper()
