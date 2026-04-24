"""
scraper.py - Comparador de insumos odontologicos Argentina
Estrategia: sitemap.xml para obtener TODAS las URLs, luego scraping individual
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

# =============================================================
#  COMO AGREGAR UNA TIENDA NUEVA
#  1. Fijate la plataforma:
#     - "mitiendanube" en el codigo HTML -> tipo: "tiendanube"
#     - "wp-content" en el HTML          -> tipo: "woocommerce"
#  2. Fijate si tiene sitemap.xml en /sitemap.xml o /sitemap_index.xml
#  3. Copia un bloque y pegalo en TIENDAS con los datos correctos
#  4. Corre ACTUALIZAR_PRECIOS.bat
#
#  COLORES: "#e63946" rojo  "#0284c7" azul  "#16a34a" verde
#           "#7c3aed" violeta  "#ea580c" naranja  "#0d9488" teal
# =============================================================

TIENDAS = [
    {
        "slug": "dentaltronador",
        "nombre": "Dental Tronador",
        "url_base": "https://www.dentaltronador.com.ar",
        "tipo": "tiendanube",
        "sitemap": "https://www.dentaltronador.com.ar/sitemap.xml",
        "filtro_sitemap": "/productos/",
        "color": "#e63946",
    },
    {
        "slug": "iow",
        "nombre": "IOW Insumos",
        "url_base": "https://www.insumosodontologicosweb.com.ar",
        "tipo": "tiendanube",
        "sitemap": "https://www.insumosodontologicosweb.com.ar/sitemap.xml",
        "filtro_sitemap": "/productos/",
        "color": "#0284c7",
    },
    {
        "slug": "odontomed",
        "nombre": "Odontomed Insumos",
        "url_base": "https://odontomedinsumos.com",
        "tipo": "woocommerce",
        "sitemap": "https://odontomedinsumos.com/product-sitemap.xml",
        "filtro_sitemap": "/producto/",
        "color": "#b45309",
    },
    {
        "slug": "orthodent",
        "nombre": "Orthodent",
        "url_base": "https://www.orthodent.com.ar",
        "tipo": "woocommerce",
        "sitemap": None,  # no tiene sitemap, usa paginado
        "url_productos": "https://www.orthodent.com.ar/todos-los-productos/",
        "color": "#457b9d",
    },
    {
        "slug": "mauri",
        "nombre": "Odontologia Mauri",
        "url_base": "https://odontologiamauri.com.ar",
        "tipo": "prestashop",
        "sitemap": None,  # no tiene sitemap, usa categorias
        "categorias": [
            "30-instrumental", "31-operatoria", "32-equipamiento",
            "33-estetica", "35-protesis", "36-endodoncia",
            "37-ortodoncia", "38-cirugia", "39-periodoncia",
            "40-rayos", "41-laboratorio", "42-odontopediatria",
        ],
        "color": "#be185d",
    },
    # NOVACEK: protegido con Cloudflare fuerte - no scrapeable
    # GRIMBERG: protegido con Cloudflare fuerte - no scrapeable
]

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "productos.json")
MAX_WORKERS = 5   # requests paralelos por tienda
DELAY = 0.3       # segundos entre requests


# =============================================================
#  HTTP - fetch con simulacion de Chrome
# =============================================================

def fetch(url, timeout=20, reintentos=2):
    """GET que simula Chrome. Reintenta hasta 2 veces ante fallos de red."""
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
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


# =============================================================
#  UTILIDADES
# =============================================================

def limpiar_precio(texto):
    """
    Convierte precios en formato argentino a float.
    Argentina usa: punto=miles, coma=decimal
    "$71.999"    -> 71999.0
    "$71.999,50" -> 71999.5
    "$1.234.567" -> 1234567.0
    """
    if not texto:
        return 0.0
    txt = str(texto).strip()
    # Extraer solo el primer bloque numerico con separadores
    match = re.search(r"[\d][\d.,]*", txt)
    if not match:
        return 0.0
    txt = match.group()

    # Formato argentino: si hay punto Y coma -> punto=miles, coma=decimal
    if "." in txt and "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    # Solo punto: puede ser miles ($71.999) o decimal ($0.99)
    elif "." in txt:
        partes = txt.split(".")
        # Si la parte decimal tiene 3 digitos -> es separador de miles
        if len(partes[-1]) == 3:
            txt = txt.replace(".", "")
        # Si tiene 1-2 digitos -> es decimal (lo dejamos)
    # Solo coma: es decimal ($71,50) o miles ($71,999)
    elif "," in txt:
        partes = txt.split(",")
        if len(partes[-1]) == 3:
            txt = txt.replace(",", "")
        else:
            txt = txt.replace(",", ".")

    try:
        v = float(txt)
        return v if 0 < v < 99_000_000 else 0.0
    except ValueError:
        return 0.0


def formatear_precio(precio):
    if not precio or precio <= 0:
        return "Consultar"
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


# =============================================================
#  SITEMAP - obtener todas las URLs de productos
# =============================================================

def obtener_urls_sitemap(sitemap_url, filtro):
    """Lee el sitemap y devuelve lista de URLs que matchean el filtro."""
    try:
        r = fetch(sitemap_url, timeout=20)
        if r.status_code != 200:
            print(f"  ! Sitemap {r.status_code}: {sitemap_url}")
            return []

        soup = BeautifulSoup(r.text, "xml")
        # Buscar sub-sitemaps (sitemap index)
        sub_sitemaps = [loc.text for loc in soup.find_all("sitemap")]
        if sub_sitemaps:
            # Es un índice, leer cada sub-sitemap
            todas = []
            for sub_url_tag in soup.find_all("loc"):
                sub_url = sub_url_tag.text
                if "sitemap" in sub_url and sub_url != sitemap_url:
                    sub_r = fetch(sub_url, timeout=20)
                    if sub_r.status_code == 200:
                        sub_soup = BeautifulSoup(sub_r.text, "xml")
                        for loc in sub_soup.find_all("loc"):
                            if filtro in loc.text:
                                todas.append(loc.text)
            return todas

        # Es un sitemap directo
        urls = [loc.text for loc in soup.find_all("loc") if filtro in loc.text]

        # Si "xml" no funcionó, intentar con html.parser (algunos sitemaps mal formados)
        if not urls:
            soup2 = BeautifulSoup(r.text, "html.parser")
            urls = [loc.text for loc in soup2.find_all("loc") if filtro in loc.text]

        # Último recurso: regex
        if not urls:
            urls = [u for u in re.findall(r'<loc>(https?://[^<]+)</loc>', r.text) if filtro in u]

        return urls

    except Exception as e:
        print(f"  ! Error sitemap {sitemap_url}: {e}")
        return []


# =============================================================
#  SCRAPING INDIVIDUAL DE PRODUCTO - Tiendanube
# =============================================================

def scrape_producto_tiendanube(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Verificar stock (Tiendanube muestra boton deshabilitado o texto sin stock)
        sin_stock = soup.select_one(".js-buy-button[disabled], .buy-button[disabled], .js-add-to-cart[disabled]")
        stock_txt = soup.select_one(".product-stock, [class*='stock'], .js-stock")
        if stock_txt and "sin stock" in stock_txt.get_text().lower():
            return None
        if sin_stock:
            return None

        # Nombre
        nombre_el = soup.select_one(".js-item-name, .product-name, h1.product-name, h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""
        if not nombre:
            return None

        # Precio - buscar primero el precio con descuento, sino el normal
        precio_el = soup.select_one(
            ".js-price-display, .product-price.js-price-display, "
            ".price-box .js-price-display, h2.js-price-display"
        )
        precio_txt = precio_el.get_text(strip=True) if precio_el else ""

        # Tiendanube a veces separa $ y numero en dos elementos
        if not precio_txt or precio_txt == "$":
            partes = soup.select(".product-price, h2.product-price")
            precio_txt = "".join(p.get_text(strip=True) for p in partes)

        precio = limpiar_precio(precio_txt)
        if not precio:
            return None

        # Imagen via og:image (más confiable)
        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""

        return hacer_producto(tienda, nombre, precio, url, imagen)

    except Exception:
        return None


# =============================================================
#  SCRAPING INDIVIDUAL DE PRODUCTO - WooCommerce
# =============================================================

def scrape_producto_woocommerce(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # JSON-LD es lo más confiable en WooCommerce
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = next((d for d in data if d.get("@type") == "Product"), None)
                if data and data.get("@type") == "Product":
                    # Verificar stock via JSON-LD
                    avail = data.get("offers", {}).get("availability", "")
                    if "OutOfStock" in avail or "Discontinued" in avail:
                        return None
                    nombre = data.get("name", "")
                    precio = limpiar_precio(str(data.get("offers", {}).get("price", 0)))
                    imagen = data.get("image", "")
                    if isinstance(imagen, list):
                        imagen = imagen[0] if imagen else ""
                    if nombre and precio:
                        return hacer_producto(tienda, nombre, precio, url, imagen)
            except Exception:
                continue

        # Verificar stock WooCommerce
        stock_el = soup.select_one(".out-of-stock, .stock.out-of-stock, p.stock.out-of-stock")
        if stock_el:
            return None

        # Fallback: HTML directo
        nombre_el = soup.select_one("h1.product_title, h1.entry-title, h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""

        precio_el = soup.select_one(
            ".price ins .woocommerce-Price-amount, "
            ".price .woocommerce-Price-amount, "
            ".price .amount, [itemprop='price']"
        )
        precio_txt = precio_el.get("content") or precio_el.get_text(strip=True) if precio_el else ""
        precio = limpiar_precio(precio_txt)

        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""

        if nombre and precio:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None

    except Exception:
        return None


# =============================================================
#  SCRAPING INDIVIDUAL DE PRODUCTO - PrestaShop (Mauri)
# =============================================================

def scrape_producto_prestashop(url, tienda):
    try:
        r = fetch(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Verificar stock PrestaShop
        avail_el = soup.select_one(".js-product-availability, #product-availability, [class*='availability']")
        if avail_el and any(w in avail_el.get_text().lower() for w in ["fuera de stock", "sin stock", "agotado", "out of stock"]):
            return None

        nombre_el = soup.select_one("h1.product-detail-name, h1[itemprop='name'], h1")
        nombre = nombre_el.get_text(strip=True) if nombre_el else ""

        precio_el = soup.select_one(
            "[itemprop='price'], .current-price span, "
            ".product-price, span[data-field='price']"
        )
        precio_txt = (precio_el.get("content") or precio_el.get_text(strip=True)) if precio_el else ""
        precio = limpiar_precio(precio_txt)

        img_el = soup.select_one('meta[property="og:image"]')
        imagen = img_el["content"] if img_el else ""

        if nombre and precio:
            return hacer_producto(tienda, nombre, precio, url, imagen)
        return None

    except Exception:
        return None


# =============================================================
#  SCRAPER CON SITEMAP (Tiendanube + WooCommerce con sitemap)
# =============================================================

def scrape_con_sitemap(tienda):
    """Obtiene URLs del sitemap y luego scrapea cada producto."""
    print(f"  Leyendo sitemap...")
    urls = obtener_urls_sitemap(tienda["sitemap"], tienda["filtro_sitemap"])

    # Filtrar URLs que sean de productos individuales (no categorias)
    urls = [u for u in urls if u.rstrip("/").split("/")[-1] != ""]
    # Excluir paginas raiz y categorias
    EXCLUIR = ["/categoria-producto/", "/product-category/", "/tag/", "/categoria/"]
    urls = [u for u in urls if not any(x in u for x in EXCLUIR)]
    urls = [u for u in urls if u.rstrip("/") not in (
        tienda["url_base"] + "/productos",
        tienda["url_base"] + "/productos/",
        tienda["url_base"] + "/producto",
        tienda["url_base"] + "/producto/",
    )]

    print(f"  {len(urls)} URLs en sitemap — scrapeando productos...")

    if not urls:
        return []

    # Elegir funcion segun tipo
    if tienda["tipo"] == "tiendanube":
        fn = scrape_producto_tiendanube
    elif tienda["tipo"] == "woocommerce":
        fn = scrape_producto_woocommerce
    else:
        fn = scrape_producto_prestashop

    productos = []
    errores = 0
    total = len(urls)

    # Scraping paralelo con ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fn, url, tienda): url for url in urls}
        for i, future in enumerate(as_completed(futures), 1):
            resultado = future.result()
            if resultado:
                productos.append(resultado)
            else:
                errores += 1
            # Progreso cada 50 productos
            if i % 50 == 0 or i == total:
                print(f"  [{i}/{total}] {len(productos)} productos OK, {errores} sin precio")
            time.sleep(DELAY / MAX_WORKERS)

    return productos


# =============================================================
#  SCRAPER PAGINADO - para tiendas sin sitemap
# =============================================================

def scrape_paginado_woocommerce(tienda):
    """Scraping paginado para WooCommerce sin sitemap."""
    productos = []
    url_base = tienda.get("url_productos", f"{tienda['url_base']}/todos-los-productos/")
    page = 1

    while True:
        url = url_base if page == 1 else re.sub(r'(/?)$', f'/page/{page}/', url_base.rstrip('/')) + '/'
        try:
            r = fetch(url, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("li.product, li.ast-article-single, article.product")
            if not items:
                break

            urls_pagina = []
            for item in items:
                # Buscar link al producto (no a categoria)
                link = item.select_one("a.woocommerce-LoopProduct-link, a.ast-loop-product__link, h2 a, h3 a, a[href]")
                if link:
                    url_prod = link["href"]
                    # Filtrar categorias y tags
                    if any(x in url_prod for x in ['/categoria-producto/', '/product-category/', '/tag/', '/categoria/']):
                        continue
                    urls_pagina.append(url_prod)

            print(f"  Página {page}: {len(urls_pagina)} productos")

            for url_prod in urls_pagina:
                prod = scrape_producto_woocommerce(url_prod, tienda)
                if prod:
                    productos.append(prod)
                time.sleep(DELAY)

            next_btn = soup.select_one("a.next, .next.page-numbers, a[rel='next']")
            if not next_btn:
                break
            page += 1

        except Exception as e:
            print(f"  ! Página {page}: {e}")
            break

    return productos


def scrape_categorias_prestashop(tienda):
    """Scraping por categorías para PrestaShop sin sitemap."""
    productos = []
    ids_vistos = set()

    for cat in tienda.get("categorias", []):
        cat_url = f"{tienda['url_base']}/{cat}"
        page = 1
        print(f"  Categoría: {cat}")

        while True:
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            try:
                r = fetch(url, timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select(".js-product, article.product-miniature")
                if not items:
                    break

                for item in items:
                    link = item.select_one("a[href]")
                    if not link:
                        continue
                    url_prod = link["href"]
                    if url_prod in ids_vistos:
                        continue
                    ids_vistos.add(url_prod)
                    prod = scrape_producto_prestashop(url_prod, tienda)
                    if prod:
                        productos.append(prod)
                    time.sleep(DELAY)

                next_btn = soup.select_one("a[rel='next'], .next, li.next a")
                if not next_btn:
                    break
                page += 1

            except Exception as e:
                print(f"  ! Cat {cat} pág {page}: {e}")
                break

    return productos


# =============================================================
#  MAIN
# =============================================================

def correr_scraper():
    todos = []
    inicio_total = time.time()

    for tienda in TIENDAS:
        inicio = time.time()
        print(f"\n{'='*50}")
        print(f"Scrapeando: {tienda['nombre']}")
        print(f"{'='*50}")

        try:
            if tienda.get("sitemap"):
                prods = scrape_con_sitemap(tienda)
            elif tienda["tipo"] == "woocommerce":
                prods = scrape_paginado_woocommerce(tienda)
            elif tienda["tipo"] == "prestashop":
                prods = scrape_categorias_prestashop(tienda)
            else:
                prods = []
        except Exception as e:
            print(f"  ERROR GENERAL: {e}")
            prods = []

        duracion = int(time.time() - inicio)
        print(f"  TOTAL: {len(prods)} productos en {duracion}s")
        todos.extend(prods)

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

    duracion_total = int(time.time() - inicio_total)
    print(f"\n{'='*50}")
    print(f"TERMINADO: {len(todos)} productos en {duracion_total}s")
    print(f"Guardado en: {DB_PATH}")
    print(f"{'='*50}")
    return todos


def cargar_productos():
    if not os.path.exists(DB_PATH):
        return correr_scraper()
    with open(DB_PATH, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    correr_scraper()
