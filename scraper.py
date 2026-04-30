name: Actualizar precios
on:
  schedule:
    - cron: '0 10 * * *'
  workflow_dispatch:
jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Clonar repositorio
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Correr scraper
        run: python scraper.py

      - name: Guardar y subir cambios
        run: |
          git config user.name "OdontoPrecio Bot"
          git config user.email "bot@odontoprecios.onrender.com"

          git add productos.json historial.json reportes.json 2>/dev/null || true

          # Si no hay cambios, salir sin error
          git diff --cached --quiet && echo "Sin cambios, nada que commitear." && exit 0

          git commit -m "Actualización automática de precios: $(date +'%d/%m/%Y')"

          # Traer el estado remoto pero descartar su productos.json (el nuestro es el correcto)
          git fetch origin main
          git merge -s ours origin/main --no-edit || true

          git push origin main
