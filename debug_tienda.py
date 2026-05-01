#!/usr/bin/env python3
"""
debug_tienda.py — Diagnostica una tienda específica de OdontoPrecio.

Uso:
    python debug_tienda.py cedent
    python debug_tienda.py iow
    python debug_tienda.py dento
    python debug_tienda.py --lista         (muestra todas las tiendas)
    python debug_tienda.py cedent --live   (scrapea en vivo, no solo analiza JSON)
"""

import sys, json, os, re, time

# ── Importar config del scraper ──
try:
    from scraper import (
        TIENDAS, fetch, limpiar_precio, hacer_producto,
        obtener_urls_sitemap, scrape_cedent, scrape_odontostore,
        BeautifulSoup
    )
    SCRAPER_OK = True
except ImportError as e:
    print(f"⚠ No se pudo importar scraper.py: {e}")
    SCRAPER_OK = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "productos.json")
REPORTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reporte_scraping.json")

SEP = "=" * 60

def colorear(texto, color):
    colores = {"rojo": "\033[91m", "verde": "\033[92m", "amarillo": "\033[93m",
               "azul": "\033[94m", "reset": "\033[0m"}
    return f"{colores.get(color,'')}{texto}{colores['reset']}"

def main():
    args = sys.argv[1:]
    if not args or "--lista" in args:
        if SCRAPER_OK:
            print("\nTiendas disponibles:")
            for t in TIENDAS:
                print(f"  {t['slug']:<20} {t['tipo']:<25} {t['nombre']}")
        else:
            print("No se pudo importar scraper.py")
        return

    slug = args[0].lower()
    modo_live = "--live" in args

    # ── Buscar tienda ──
    tienda = None
    if SCRAPER_OK:
        tienda = next((t for t in TIENDAS if t["slug"] == slug), None)

    if not tienda:
        print(f"❌ Tienda '{slug}' no encontrada.")
        if SCRAPER_OK:
            slugs = [t["slug"] for t in TIENDAS]
            print(f"   Disponibles: {', '.join(slugs)}")
        return

    print(f"\n{SEP}")
    print(f"DIAGNÓSTICO: {tienda['nombre']} ({slug})")
    print(f"URL: {tienda['url_base']}")
    print(f"Tipo: {tienda['tipo']}")
    print(SEP)

    # ── PARTE 1: Análisis del JSON actual ──
    print(f"\n{'─'*40}")
    print("PARTE 1: Estado en productos.json")
    print(f"{'─'*40}")

    if not os.path.exists(DB_PATH):
        print(colorear("❌ productos.json no existe — correr el scraper primero", "rojo"))
    else:
        with open(DB_PATH, encoding="utf-8") as f:
            todos = json.load(f)

        prods_tienda = [p for p in todos if p.get("tienda_slug") == slug]
        print(f"Total en JSON: {len(todos)} productos")
        print(f"De esta tienda: {colorear(str(len(prods_tienda)), 'verde' if len(prods_tienda) > 0 else 'rojo')}")

        if prods_tienda:
            # Análisis de calidad
            sin_precio = [p for p in prods_tienda if not p.get("precio") or p["precio"] <= 0]
            sin_imagen = [p for p in prods_tienda if not p.get("imagen")]
            sin_url = [p for p in prods_tienda if not p.get("url")]
            nombres_cortos = [p for p in prods_tienda if len(p.get("nombre","")) < 5]

            print(f"\nCalidad de datos:")
            print(f"  Con precio:   {len(prods_tienda)-len(sin_precio)}/{len(prods_tienda)}")
            print(f"  Con imagen:   {len(prods_tienda)-len(sin_imagen)}/{len(prods_tienda)}")
            print(f"  Con URL:      {len(prods_tienda)-len(sin_url)}/{len(prods_tienda)}")
            print(f"  Nombre largo: {len(prods_tienda)-len(nombres_cortos)}/{len(prods_tienda)}")

            print(f"\nPrimeros 5 productos:")
            for p in prods_tienda[:5]:
                print(f"  [{p.get('precio_fmt','?')}] {p.get('nombre','?')[:60]}")
                print(f"    ID: {p.get('id','?')}")
                print(f"    URL: {p.get('url','?')[:70]}")

            # Verificar ID format
            ids = [p.get("id","") for p in prods_tienda]
            ids_con_md5 = [i for i in ids if len(i.split("_")[-1]) == 16]
            print(f"\nIDs con MD5 (estables): {len(ids_con_md5)}/{len(ids)}")
            if len(ids_con_md5) < len(ids):
                print(colorear("  ⚠ Algunos IDs son hash no determinístico — historial puede fallar", "amarillo"))

            # Historial
            hist_path = os.path.join(os.path.dirname(DB_PATH), "historial.json")
            if os.path.exists(hist_path):
                with open(hist_path) as f:
                    hist = json.load(f)
                ids_con_hist = sum(1 for p in prods_tienda if p.get("id") in hist)
                print(f"  Con historial de precios: {ids_con_hist}/{len(prods_tienda)}")
        else:
            print(colorear(f"\n❌ PROBLEMA: {slug} no tiene ningún producto en el JSON", "rojo"))
            print("  → El scraper no guardó nada para esta tienda")
            print("  → Posibles causas:")
            print("    1. El scraper dio 0 productos (selectores CSS rotos)")
            print("    2. Todos los productos fueron filtrados (sin precio/stock)")
            print("    3. Error no capturado durante el scraping")

    # ── PARTE 2: Último reporte de scraping ──
    print(f"\n{'─'*40}")
    print("PARTE 2: Último reporte de scraping")
    print(f"{'─'*40}")

    if not os.path.exists(REPORTE_PATH):
        print("⚠ reporte_scraping.json no existe — correr el scraper con la nueva versión")
    else:
        with open(REPORTE_PATH) as f:
            reporte = json.load(f)

        print(f"Fecha del reporte: {reporte.get('fecha', '?')}")
        info = next((t for t in reporte.get("tiendas", []) if t["slug"] == slug), None)
        if info:
            estado_color = {"ok": "verde", "sin_productos": "rojo", "error_fatal": "rojo",
                           "cobertura_baja": "amarillo", "bajo": "amarillo"}.get(info["estado"], "reset")
            print(f"Estado: {colorear(info['estado'], estado_color)}")
            print(f"Productos scrapeados: {info['productos']}")
            print(f"Estimados reales: {info.get('estimados', '?')}")
            print(f"Cobertura: {info.get('cobertura_pct', '?')}%")
            print(f"Reutilizados cache: {info.get('reutilizados_cache', 0)}")
            print(f"Errores individuales: {info.get('errores', 0)}")
            print(f"Duración: {info['duracion_s']}s")
            print(f"Método: {info['metodo']} / estimación: {info.get('metodo_estimacion','?')}")
            if info.get("warnings"):
                print("Warnings:")
                for w in info["warnings"]:
                    print(f"  {colorear(w, 'amarillo')}")
            if info.get("error_detalle"):
                print(colorear(f"ERROR: {info['error_detalle']}", "rojo"))
            if info.get("traceback"):
                print("Traceback (últimas líneas):")
                print(info["traceback"][-500:])
        else:
            print(f"⚠ '{slug}' no encontrado en el reporte")

    # ── PARTE 3: Verificación de búsqueda en app ──
    print(f"\n{'─'*40}")
    print("PARTE 3: Verificación de búsqueda")
    print(f"{'─'*40}")

    if os.path.exists(DB_PATH):
        with open(DB_PATH) as f:
            todos = json.load(f)
        prods_tienda = [p for p in todos if p.get("tienda_slug") == slug]
        if prods_tienda:
            # Simular normalización del buscador
            import unicodedata
            def normalizar(texto):
                t = unicodedata.normalize("NFD", texto.lower())
                t = "".join(c for c in t if unicodedata.category(c) != "Mn")
                t = re.sub(r"[-./()%,;:!?\\[\\]]", " ", t)
                return re.sub(r" +", " ", t).strip()

            nombres_norm = [normalizar(p["nombre"]) for p in prods_tienda]
            print(f"Nombres normalizados (primeros 3):")
            for i, (p, n) in enumerate(zip(prods_tienda[:3], nombres_norm[:3])):
                print(f"  Original: '{p['nombre']}'")
                print(f"  Norm:     '{n}'")

            # Test búsqueda básica
            query_test = tienda["nombre"].split()[0].lower()  # primera palabra del nombre tienda
            print(f"\nTest búsqueda con '{query_test}':")
            encontrados = [p for p, n in zip(prods_tienda, nombres_norm) if query_test in n]
            print(f"  Encontrados: {len(encontrados)}")

            # Verificar tienda_nombre correcto
            nombres_tienda = set(p.get("tienda_nombre") for p in prods_tienda)
            print(f"\ntienda_nombre en JSON: {nombres_tienda}")
            print(f"tienda.nombre en config: '{tienda['nombre']}'")
            if tienda["nombre"] in nombres_tienda:
                print(colorear("  ✅ Coincide — la tienda aparece correctamente en el filtro", "verde"))
            else:
                print(colorear("  ❌ No coincide — la tienda puede no mostrarse correctamente", "rojo"))

    # ── PARTE 4: Test en vivo (opcional) ──
    if modo_live and SCRAPER_OK:
        print(f"\n{'─'*40}")
        print("PARTE 4: Scraping en vivo (--live)")
        print(f"{'─'*40}")
        print(f"Scrapeando {tienda['nombre']} ahora mismo...")
        print("(Esto puede tardar varios minutos)\n")

        from scraper import (
            scrape_con_sitemap, scrape_paginado_woocommerce,
            scrape_categorias_prestashop, scrape_carrizo,
            scrape_dentalab, scrape_odontostore, scrape_shopify
        )

        inicio = time.time()
        tipo = tienda["tipo"]
        prods_live = []
        try:
            if tipo in ("tiendanube", "woocommerce") and tienda.get("sitemap"):
                prods_live = scrape_con_sitemap(tienda)
            elif tipo == "shopify":
                prods_live = scrape_shopify(tienda)
            elif tipo == "woocommerce_paginado":
                prods_live = scrape_paginado_woocommerce(tienda)
            elif tipo == "prestashop":
                prods_live = scrape_categorias_prestashop(tienda)
            elif tipo == "carrizo":
                prods_live = scrape_carrizo(tienda)
            elif tipo == "dentalab":
                prods_live = scrape_dentalab(tienda)
            elif tipo == "odontostore":
                prods_live = scrape_odontostore(tienda)
            elif tipo == "cedent":
                prods_live = scrape_cedent(tienda)
        except Exception as e:
            import traceback
            print(colorear(f"❌ ERROR: {e}", "rojo"))
            print(traceback.format_exc())

        duracion = round(time.time() - inicio, 1)
        print(f"\nResultado scraping en vivo:")
        print(f"  Productos: {colorear(str(len(prods_live)), 'verde' if len(prods_live) > 0 else 'rojo')}")
        print(f"  Duración: {duracion}s")

        if prods_live:
            print(f"\nEjemplos (primeros 5):")
            for p in prods_live[:5]:
                print(f"  [{p.get('precio_fmt','?')}] {p.get('nombre','?')[:60]}")
        else:
            print(colorear("\n❌ 0 productos en live — problema confirmado en scraper", "rojo"))

    # ── PARTE 5: Diagnóstico de conectividad ──
    print(f"\n{'─'*40}")
    print("PARTE 5: Conectividad")
    print(f"{'─'*40}")
    if SCRAPER_OK:
        try:
            r = fetch(tienda["url_base"], timeout=10)
            print(f"  HTTP GET {tienda['url_base']}: {colorear(str(r.status_code), 'verde' if r.status_code == 200 else 'rojo')}")
            print(f"  Tamaño respuesta: {len(r.text)} bytes")
            if r.status_code == 200:
                print(f"  ✅ Sitio accesible")
                # Detectar plataforma
                if "tiendanube" in r.text.lower() or "tienda-nube" in r.text.lower():
                    print(f"  Plataforma detectada: TiendaNube")
                elif "woocommerce" in r.text.lower():
                    print(f"  Plataforma detectada: WooCommerce")
                elif "odoo" in r.text.lower() or "o_wsale" in r.text.lower():
                    print(f"  Plataforma detectada: Odoo")
                elif "prestashop" in r.text.lower():
                    print(f"  Plataforma detectada: PrestaShop")
                elif "shopify" in r.text.lower():
                    print(f"  Plataforma detectada: Shopify")
            elif r.status_code == 403:
                print(colorear(f"  ⚠ 403 — Sitio bloquea el scraper", "rojo"))
            elif r.status_code == 429:
                print(colorear(f"  ⚠ 429 — Rate limit activo", "amarillo"))
        except Exception as e:
            print(colorear(f"  ❌ Error de conexión: {e}", "rojo"))

        # Test primera categoría si aplica
        if tienda.get("categorias_urls"):
            primera_cat = tienda["url_base"] + tienda["categorias_urls"][0]
            try:
                r2 = fetch(primera_cat, timeout=10)
                print(f"\n  Primera categoría: {tienda['categorias_urls'][0]}")
                print(f"  HTTP: {colorear(str(r2.status_code), 'verde' if r2.status_code == 200 else 'rojo')}")
                if r2.status_code == 200:
                    soup = BeautifulSoup(r2.text, "lxml")
                    # Buscar cualquier card de producto
                    cards_encontradas = {}
                    for sel in [".o_wsale_products_grid_item", ".oe_product_cart",
                                "article.product_item", ".js_product", "[data-product_id]",
                                "div[itemtype*='Product']", ".product-item"]:
                        n = len(soup.select(sel))
                        if n > 0:
                            cards_encontradas[sel] = n
                    if cards_encontradas:
                        print(f"  Selectores que funcionan:")
                        for sel, n in cards_encontradas.items():
                            print(f"    {colorear(sel, 'verde')}: {n} elementos")
                    else:
                        print(colorear("  ⚠ Ningún selector de producto encontró nada", "rojo"))
                        # Mostrar clases CSS relevantes para debug
                        clases = set()
                        for tag in soup.find_all(class_=True)[:100]:
                            for c in tag.get("class", []):
                                if any(k in c for k in ["product","wsale","oe_","shop","item","card"]):
                                    clases.add(c)
                        if clases:
                            print(f"  Clases CSS relevantes en la página:")
                            for c in sorted(clases)[:15]:
                                print(f"    .{c}")
                elif r2.status_code == 404:
                    print(colorear(f"  ❌ 404 — Esta categoría no existe", "rojo"))
            except Exception as e:
                print(colorear(f"  Error al acceder categoría: {e}", "rojo"))

    print(f"\n{SEP}")
    print("FIN DEL DIAGNÓSTICO")
    print(SEP)

if __name__ == "__main__":
    main()
