"""
╔══════════════════════════════════════════════════════════════╗
║       TUNISIANET SCRAPER — scrape_tunisianet.py              ║
║  Run:  python scrape_tunisianet.py                           ║
╚══════════════════════════════════════════════════════════════╝

HOW TO ADD MORE CATEGORIES
───────────────────────────
Tunisianet category URLs follow the pattern:
    https://www.tunisianet.com.tn/<ID>-<slug>

To find more: open tunisianet.com.tn, navigate to the category,
and copy the URL from the address bar.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scraper.core import MarketplaceScraper
from scraper.exporters import export_json, export_csv

# ─────────────────────────────────────────────────────────────
#  ▼▼▼  EDIT THIS SECTION  ▼▼▼
# ─────────────────────────────────────────────────────────────

_FIELDS = {
    "title":        {"selector": "h2.product-title a"},
    "price":        {"selector": "span.price", "type": "price"},
    "availability": {"selector": "span.product-availability"},
    "item_url":     {"selector": "h2.product-title a",    "type": "href", "absolute": True},
    "image_url":    {"selector": "img.product-thumbnail", "type": "src",  "absolute": True},
}

_PAGINATION = {
    "strategy":   "page_param",
    "page_param": "page",
    "max_pages":  20,
}

_EXTRA_HEADERS = {
    "Referer":         "https://www.tunisianet.com.tn/",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def make_source(base_url: str) -> dict:
    return {
        "base_url":      base_url,
        "item_selector": "article.product-miniature",
        "fields":        _FIELDS,
        "pagination":    _PAGINATION,
        "mode":          "static",
        "extra_headers": _EXTRA_HEADERS,
        "cookies":       {},
    }


# All URLs verified from tunisianet.com.tn live page
CATEGORIES: list[tuple[str, str]] = [
    # ── Ordinateurs ───────────────────────────────────────────
    ("PC Portables",              "https://www.tunisianet.com.tn/301-pc-portable-tunisie"),
    ("PC Portables Pro",          "https://www.tunisianet.com.tn/703-pc-portable-pro"),
    ("PC Portables Gamer",        "https://www.tunisianet.com.tn/681-pc-portable-gamer"),
    ("PC de Bureau",              "https://www.tunisianet.com.tn/373-pc-de-bureau"),
    ("PC de Bureau Gamer",        "https://www.tunisianet.com.tn/682-pc-de-bureau-gamer"),
    ("PC Tout-en-un",             "https://www.tunisianet.com.tn/686-pc-tout-en-un"),
    ("Ecrans PC",                 "https://www.tunisianet.com.tn/667-ecran-pc-tunisie"),

    # ── Composants & Stockage ─────────────────────────────────
    ("Composants Informatique",   "https://www.tunisianet.com.tn/406-composant-informatique"),
    ("Carte Graphique",           "https://www.tunisianet.com.tn/410-carte-graphique-tunisie"),
    ("Barrette Mémoire",          "https://www.tunisianet.com.tn/409-barrette-memoire"),
    ("Carte Mère",                "https://www.tunisianet.com.tn/420-carte-mere"),
    ("Processeur",                "https://www.tunisianet.com.tn/421-processeur"),
    ("Boîtier PC",                "https://www.tunisianet.com.tn/425-boitier"),
    ("Alimentation PC",           "https://www.tunisianet.com.tn/423-boite-alimentation-pc-tunisie"),
    ("Refroidisseur",             "https://www.tunisianet.com.tn/500-refroidisseur"),
    ("Disques SSD",               "https://www.tunisianet.com.tn/379-disques-ssd"),
    ("Disque Dur Interne",        "https://www.tunisianet.com.tn/408-disque-dur-interne"),
    ("Disque Dur Externe",        "https://www.tunisianet.com.tn/313-disque-dur-externe-tunisie"),
    ("Clé USB",                   "https://www.tunisianet.com.tn/314-cle-usb-tunisie"),
    ("Carte Mémoire",             "https://www.tunisianet.com.tn/315-carte-memoire-tunisie"),

    # ── Périphériques & Accessoires ───────────────────────────
    ("Claviers",                  "https://www.tunisianet.com.tn/704-claviers"),
    ("Souris",                    "https://www.tunisianet.com.tn/334-souris-informatique"),
    ("Ensemble Clavier & Souris", "https://www.tunisianet.com.tn/332-ensemble-clavier-et-souris"),
    ("Casques & Écouteurs",       "https://www.tunisianet.com.tn/338-casque-ecouteurs"),
    ("Webcam",                    "https://www.tunisianet.com.tn/336-webcam"),
    ("Microphone",                "https://www.tunisianet.com.tn/485-microphone"),
    ("Tapis Souris",              "https://www.tunisianet.com.tn/488-tapis-souris-tunisie"),
    ("Hub USB & Lecteur Carte",   "https://www.tunisianet.com.tn/498-hub-usb-lecteur-carte-tunisie"),
    ("Dock Station",              "https://www.tunisianet.com.tn/683-dock-station-tunisie"),
    ("Sac à Dos",                 "https://www.tunisianet.com.tn/331-sac-a-dos-tunisie"),

    # ── Impression ────────────────────────────────────────────
    ("Imprimantes",               "https://www.tunisianet.com.tn/316-imprimante-en-tunisie"),
    ("Imprimante Laser",          "https://www.tunisianet.com.tn/318-imprimante-et-multifonction-laser"),
    ("Imprimante Jet d'Encre",    "https://www.tunisianet.com.tn/321-imprimante-et-multifonction-jet-d-encre"),
    ("Imprimante Réservoir",      "https://www.tunisianet.com.tn/455-imprimante-a-reservoir-integre"),
    ("Photocopieur",              "https://www.tunisianet.com.tn/444-photocopieur-tunisie"),
    ("Scanner",                   "https://www.tunisianet.com.tn/326-scanner-informatique"),
    ("Consommables Imprimante",   "https://www.tunisianet.com.tn/317-consommable-imprimante-tunisie"),

    # ── Réseaux & Sécurité ────────────────────────────────────
    ("Réseaux",                   "https://www.tunisianet.com.tn/438-reseau"),
    ("Switch, Routeurs & AP",     "https://www.tunisianet.com.tn/441-switch-routeurs-point-d-acces"),
    ("Clé WiFi & Bluetooth",      "https://www.tunisianet.com.tn/443-cle-wifi-bluetooth"),
    ("Onduleur",                  "https://www.tunisianet.com.tn/380-onduleur"),
    ("Vidéosurveillance",         "https://www.tunisianet.com.tn/509-videosurveillance-tunisie"),
    ("Câbles & Connectique",      "https://www.tunisianet.com.tn/349-cable-connectique-informatique"),
    ("Multiprise",                "https://www.tunisianet.com.tn/674-multiprise"),

    # ── Téléphonie ────────────────────────────────────────────
    ("Smartphones",               "https://www.tunisianet.com.tn/596-smartphone-tunisie"),
    ("Tablettes",                 "https://www.tunisianet.com.tn/515-tablette"),
    ("Tablette Graphique",        "https://www.tunisianet.com.tn/728-tablette-graphique"),
    ("Smartwatch",                "https://www.tunisianet.com.tn/650-smartwatch"),
    ("Power Bank",                "https://www.tunisianet.com.tn/636-power-bank-tunisie"),
    ("Accessoires Téléphone",     "https://www.tunisianet.com.tn/378-accessoire-telephonie-mobile-tunisie"),
    ("Téléphone Fixe",            "https://www.tunisianet.com.tn/462-telephone-fixe"),

    # ── TV / Son / Image ──────────────────────────────────────
    ("Téléviseurs",               "https://www.tunisianet.com.tn/665-televiseurs"),
    ("Vidéoprojecteurs",          "https://www.tunisianet.com.tn/666-videoprojecteurs"),
    ("Home Cinéma",               "https://www.tunisianet.com.tn/685-ensemble-home-cinema-tunise"),
    ("Haut-Parleurs",             "https://www.tunisianet.com.tn/687-haut-parleur"),
    ("Barre de Son",              "https://www.tunisianet.com.tn/690-barre-de-son"),
    ("Récepteurs Numériques",     "https://www.tunisianet.com.tn/668-recepteur"),
    ("Appareils Photo",           "https://www.tunisianet.com.tn/370-appareil-photo-tunisie"),

    # ── Gaming ────────────────────────────────────────────────
    ("Consoles de Jeux",          "https://www.tunisianet.com.tn/466-console-de-jeux"),
    ("Manettes de Jeux",          "https://www.tunisianet.com.tn/341-manettes-de-jeux"),
    ("Accessoires Consoles",      "https://www.tunisianet.com.tn/468-accessoires-pour-consoles"),

    # ── Électroménager ────────────────────────────────────────
    ("Climatiseurs",              "https://www.tunisianet.com.tn/457-climatiseur-tunisie-chaud-froid"),
    ("Réfrigérateur",             "https://www.tunisianet.com.tn/525-refrigerateur-tunisie"),
    ("Congélateur",               "https://www.tunisianet.com.tn/526-congelateur-tunisie"),
    ("Machine à Laver",           "https://www.tunisianet.com.tn/528-machine-a-laver"),
    ("Lave-Vaisselle",            "https://www.tunisianet.com.tn/541-lave-vaisselle-tunisie"),
    ("Micro-Onde",                "https://www.tunisianet.com.tn/742-micro-onde"),
    ("Cuisinière",                "https://www.tunisianet.com.tn/736-cuisiniere-tunisie"),
    ("Aspirateur",                "https://www.tunisianet.com.tn/558-aspirateur-tunisie-vapeur"),
    ("Cafetière",                 "https://www.tunisianet.com.tn/537-cafetiere-tunisie"),
    ("Blender",                   "https://www.tunisianet.com.tn/529-blender-tunisie"),
    ("Friteuse & Air Fryer",      "https://www.tunisianet.com.tn/744-airfryer-tunisie"),
    ("Chauffage",                 "https://www.tunisianet.com.tn/553-chauffage-tunisie"),
    ("Ventilateur",               "https://www.tunisianet.com.tn/713-ventilateur-tunisie"),
]

OUTPUT_FORMAT = "both"
OUTPUT_PREFIX = "tunisianet_results"
SOURCE_NAME   = "tunisianet.com.tn"

# ─────────────────────────────────────────────────────────────
#  ▲▲▲  STOP EDITING HERE  ▲▲▲
# ─────────────────────────────────────────────────────────────


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    Path("output").mkdir(exist_ok=True)

    # Use a timestamped DB so each run starts completely fresh.
    # The old results.db was causing ALL categories after the first to return
    # 0 products because their item IDs were already in self._seen from the DB.
    from datetime import datetime
    db_path = f"output/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

    all_items = []
    category_stats: list[tuple[str, int]] = []

    async with MarketplaceScraper(
        requests_per_second=1.5,
        burst=3,
        concurrency=5,
        max_retries=4,
        db_path=db_path,
    ) as scraper:
        for cat_name, cat_url in CATEGORIES:
            print(f"\n── {cat_name} ──────────────────────────────────────────")
            scraper.reset_seen()   # clear dedup set so this category starts fresh
            source = make_source(cat_url)
            items = await scraper.scrape_source(source)

            for item in items:
                item.extra["source"]   = SOURCE_NAME
                item.extra["category"] = cat_name

            all_items.extend(items)
            category_stats.append((cat_name, len(items)))
            print(f"   ✔ {cat_name}: {len(items)} products")

        scraper.print_stats()

    if not all_items:
        print("\n⚠  No items were scraped.")
        return

    if OUTPUT_FORMAT in ("json", "both"):
        export_json(all_items, f"output/{OUTPUT_PREFIX}.json")
        print(f"✔  output/{OUTPUT_PREFIX}.json")

    if OUTPUT_FORMAT in ("csv", "both"):
        export_csv(all_items, f"output/{OUTPUT_PREFIX}.csv")
        print(f"✔  output/{OUTPUT_PREFIX}.csv")

    print(f"\n✔  {db_path}  (SQLite — {len(all_items)} total items stored)")
    print(f"\n── Done — {len(all_items)} total products ──────────────")
    print("\n   Products per category:")
    for cat_name, count in category_stats:
        print(f"      {cat_name}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
