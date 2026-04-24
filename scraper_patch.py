# Read original
with open('/home/claude/odontoprecio/scraper.py', 'r') as f:
    content = f.read()

prestashop_func = '''

def scrape_prestashop(tienda: dict) -> list:
    """Scraper para tiendas en PrestaShop (ej: Odontologia Mauri)."""
    productos = []
    page = 1
    while True:
        url = f"{tienda['url_base']}/todos-los-productos?page={page}" if page > 1 else f"{tienda['url_base']}/todos-los-productos"
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("article.product-miniature, .product-miniature, .js-product")
            if not items:
                break
            for item in items:
                try:
                    nombre_el = item.select_one(".product-title, h2, h3, .product-name a")
                    nombre = nombre_el.get_text(strip=True) if nombre_el else None
                    precio_el = item.select_one(".price, .product-price-and-shipping .price")
                    precio_txt = precio_el.get_text(strip=True) if precio_el else ""
                    precio = limpiar_precio(precio_txt)
                    link_el = item.select_one("a[href]")
                    url_prod = link_el["href"] if link_el else ""
                    img_el = item.select_one("img")
                    imagen = img_el.get("src") or img_el.get("data-src", "") if img_el else ""
                    if nombre and precio:
                        productos.append({
                            "id": f"{tienda['slug']}_{abs(hash(url_prod))}",
                            "nombre": nombre,
                            "precio": precio,
                            "precio_fmt": formatear_precio(precio),
                            "url": url_prod,
                            "imagen": imagen,
                            "tienda_slug": tienda["slug"],
                            "tienda_nombre": tienda["nombre"],
                            "tienda_color": tienda["color"],
                            "actualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        })
                except Exception:
                    continue
            next_btn = soup.select_one("a[rel=\'next\'], .next, li.next a")
            if not next_btn:
                break
            page += 1
            import time as t2; t2.sleep(1)
        except Exception as e:
            print(f"  Warning: {tienda['nombre']} pag {page}: {e}")
            break
    return productos

'''

new_content = content.replace('\ndef scrape_woocommerce', prestashop_func + '\ndef scrape_woocommerce', 1)

with open('/home/claude/odontoprecio/scraper.py', 'w') as f:
    f.write(new_content)

print("Done, new length:", len(new_content))
