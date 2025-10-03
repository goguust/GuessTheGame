# core/services/scraper.py
# -*- coding: utf-8 -*-
"""
Scraper per https://netapps.ocfl.net/BestJail/
- Scorre una lista di filtri (es. lettere 'a'..'z')
- getInmates/{filtro}      -> bookingNumber + inmateName
- getInmateDetails/{bk}    -> nome, età, immagine (data URL / base64 / URL)
- getCharges/{bk}          -> lista charges (salvati su tabella Charge, FK → Inmate)
"""

import os
import re
import uuid
import base64
import string
import requests
from urllib.parse import urljoin

from django.conf import settings
from core.models import Inmate, Charge  # <-- importa anche Charge

BASE = "https://netapps.ocfl.net/BestJail/Home/"
URL_SEARCH   = BASE + "getInmates/{}"
URL_DETAILS  = BASE + "getInmateDetails/{}"
URL_CHARGES  = BASE + "getCharges/{}"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://netapps.ocfl.net",
    "Referer": "https://netapps.ocfl.net/BestJail/Home/Inmates",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
TIMEOUT = 30


def _split_name(inmate_name: str):
    """'ADAMS, TODERICK LEONARD JR' -> ('TODERICK LEONARD JR', 'ADAMS')"""
    inmate_name = (inmate_name or "").strip()
    inmate_name = re.sub(r"\s+", " ", inmate_name)
    last, first = "", ""
    if "," in inmate_name:
        last, first = [x.strip() for x in inmate_name.split(",", 1)]
    else:
        parts = inmate_name.split()
        if len(parts) >= 2:
            first = parts[-1]
            last  = " ".join(parts[:-1])
        else:
            first = inmate_name
    return first, last


def _save_image_from_data(data: str) -> str | None:
    """
    Supporta:
      - data URL: 'data:image/png;base64,...'
      - base64 raw: 'iVBORw0...'
      - URL http/https: download
    Ritorna path relativo 'inmates/<uuid>.<ext>' (per Django), oppure None.
    """
    if not data:
        return None

    # URL assoluto
    if data.startswith(("http://", "https://")):
        try:
            r = requests.get(data, timeout=TIMEOUT)
            r.raise_for_status()
            content = r.content
            ext = ".jpg"
            ct = r.headers.get("Content-Type", "")
            if "png" in ct:
                ext = ".png"
            fname = f"{uuid.uuid4().hex}{ext}"
            folder = os.path.join(settings.MEDIA_ROOT, "inmates")
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, fname)
            with open(dest, "wb") as f:
                f.write(content)
            return f"inmates/{fname}"
        except Exception as e:
            print(f"[IMG][ERR] download url: {e}")
            return None

    # data URL "data:image/..;base64,...."
    if data.startswith("data:image"):
        try:
            header, b64 = data.split(",", 1)
            ext = ".jpg"
            if "png" in header.lower():
                ext = ".png"
            content = base64.b64decode(b64)
            fname = f"{uuid.uuid4().hex}{ext}"
            folder = os.path.join(settings.MEDIA_ROOT, "inmates")
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, fname)
            with open(dest, "wb") as f:
                f.write(content)
            return f"inmates/{fname}"
        except Exception as e:
            print(f"[IMG][ERR] data url: {e}")
            return None

    # base64 raw
    try:
        content = base64.b64decode(data)
        fname = f"{uuid.uuid4().hex}.png"
        folder = os.path.join(settings.MEDIA_ROOT, "inmates")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, fname)
        with open(dest, "wb") as f:
            f.write(content)
        return f"inmates/{fname}"
    except Exception as e:
        print(f"[IMG][ERR] raw b64: {e}")
        return None


def _fetch_json(session: requests.Session, url: str):
    r = session.post(url, data="{}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def run_scrape(
    filters: list[str] | None = None,
    limit: int | None = None,
    reset: bool = False,
    verbose: bool = True,
    charge_filter_contains: str | None = None,  # es. "CANNABIS" per filtrare
):
    """
    - filters: lista lettere (es. ['a','d']); None => a..z
    - limit: massimo detenuti totali; 0/None => tutti
    - reset: svuota DB prima
    - charge_filter_contains: se valorizzato, salva SOLO i charges che contengono questa stringa (case-insensitive). Es: "CANNABIS"
    """
    if reset:
        Inmate.objects.all().delete()
        Charge.objects.all().delete()
        if verbose: print("[SCRAPER] DB resettato.")

    if not filters:
        filters = list(string.ascii_lowercase)

    session = requests.Session()
    session.headers.update(HEADERS)

    scanned = created = updated = 0

    for flt in filters:
        url = URL_SEARCH.format(flt)
        if verbose: print(f"[SCRAPER] Filtro '{flt}' -> {url}")

        try:
            results = _fetch_json(session, url)
        except Exception as e:
            print(f"[SCRAPER][ERR] search {flt}: {e}")
            continue

        for row in results:
            booking = str(row.get("bookingNumber") or "").strip()
            full_name = row.get("inmateName", "").strip()
            first, last = _split_name(full_name)

            # --- Dettagli
            try:
                det = _fetch_json(session, URL_DETAILS.format(booking))
                det0 = det[0] if isinstance(det, list) and det else {}
            except Exception as e:
                print(f"[SCRAPER][ERR] details {booking}: {e}")
                det0 = {}

            age = None
            birth_field = det0.get("BIRTH")
            try:
                age = int(str(birth_field).strip()) if birth_field not in (None, "", "NULL") else None
            except Exception:
                age = None

            image_field = det0.get("IMAGE") or det0.get("Image") or ""
            image_rel = _save_image_from_data(image_field) if image_field else None

            # --- Salva/aggiorna Inmate
            inmate, was_created = Inmate.objects.update_or_create(
                booking_number=booking,
                defaults={
                    "first_name": first,
                    "last_name":  last,
                    "age":        age,
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1

            if image_rel and not inmate.image:
                inmate.image.name = image_rel
                inmate.save(update_fields=["image"])

            # --- Charges
            try:
                charges = _fetch_json(session, URL_CHARGES.format(booking))
            except Exception as e:
                print(f"[SCRAPER][ERR] charges {booking}: {e}")
                charges = []

            # puliamo i charges esistenti per l'inmate e reinseriamo (più semplice e coerente)
            Charge.objects.filter(inmate=inmate).delete()

            for ch in charges:
                desc   = (ch.get("Charge") or "").strip()
                if not desc:
                    continue
                if charge_filter_contains:
                    if charge_filter_contains.upper() not in desc.upper():
                        continue  # filtra se richiesto (es. solo 'CANNABIS')

                bond   = (ch.get("BondAmount") or "").strip()
                case   = (ch.get("CourtCaseNumber") or "").strip()
                court  = (ch.get("CourtLocation") or "").strip()
                note   = (ch.get("Note") or "").strip()

                Charge.objects.create(
                    inmate=inmate,
                    charge=desc,
                    bond_amount=bond,
                    court_case_number=case,
                    court_location=court,
                    note=note,
                )

            scanned += 1
            if limit and scanned >= limit:
                stats = {"scanned": scanned, "created": created, "updated": updated}
                if verbose: print(f"[SCRAPER] DONE (limit raggiunto): {stats}")
                return stats

    stats = {"scanned": scanned, "created": created, "updated": updated}
    if verbose: print(f"[SCRAPER] DONE: {stats}")
    return stats
