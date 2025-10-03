# core/services/scraper.py
# -*- coding: utf-8 -*-
"""
Scraper per https://netapps.ocfl.net/BestJail/
- Scorre una lista di filtri (es. lettere 'a'..'z')
- getInmates/{filtro}      -> bookingNumber + inmateName
- getInmateDetails/{bk}    -> nome, età, immagine (base64 nel campo "IMAGE")
- getCharges/{bk}          -> lista charges (salvati su tabella Charge, FK → Inmate)

⚠️ NOTA: Le immagini non vengono più salvate su disco o DB.
         Quando servono, si ottengono live via fetch_inmate_details().
"""

import re
import string
import requests
from django.conf import settings
from core.models import Inmate, Charge

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


def _fetch_json(session: requests.Session, url: str):
    """Effettua una POST vuota e ritorna JSON."""
    r = session.post(url, data="{}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_inmate_details(booking_number: str) -> dict:
    """
    Ritorna i dettagli dell'inmate come JSON (incluso il campo IMAGE in base64).
    """
    try:
        resp = requests.post(URL_DETAILS.format(booking_number), data="{}", headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if isinstance(data, list) and data else {}
    except Exception as e:
        print(f"[SCRAPER][ERR] fetch_inmate_details {booking_number}: {e}")
        return {}


def run_scrape(
    filters: list[str] | None = None,
    limit: int | None = None,
    reset: bool = False,
    verbose: bool = True,
    charge_filter_contains: str | None = None,
):
    """
    - filters: lista lettere (es. ['a','d']); None => a..z
    - limit: massimo detenuti totali; 0/None => tutti
    - reset: svuota DB prima
    - charge_filter_contains: se valorizzato, salva SOLO i charges che contengono questa stringa (case-insensitive).
    """
    if reset:
        Inmate.objects.all().delete()
        Charge.objects.all().delete()
        if verbose: 
            print("[SCRAPER] DB resettato.")

    if not filters:
        filters = list(string.ascii_lowercase)

    session = requests.Session()
    session.headers.update(HEADERS)

    scanned = created = updated = 0

    for flt in filters:
        url = URL_SEARCH.format(flt)
        if verbose: 
            print(f"[SCRAPER] Filtro '{flt}' -> {url}")

        try:
            results = _fetch_json(session, url)
        except Exception as e:
            print(f"[SCRAPER][ERR] search {flt}: {e}")
            continue

        for row in results:
            booking = str(row.get("bookingNumber") or "").strip()
            full_name = row.get("inmateName", "").strip()
            first, last = _split_name(full_name)

            # --- Dettagli (per età)
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

            # --- Salva/aggiorna Inmate (senza immagine)
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

            # --- Charges
            try:
                charges = _fetch_json(session, URL_CHARGES.format(booking))
            except Exception as e:
                print(f"[SCRAPER][ERR] charges {booking}: {e}")
                charges = []

            Charge.objects.filter(inmate=inmate).delete()

            for ch in charges:
                desc   = (ch.get("Charge") or "").strip()
                if not desc:
                    continue
                if charge_filter_contains:
                    if charge_filter_contains.upper() not in desc.upper():
                        continue

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
                if verbose: 
                    print(f"[SCRAPER] DONE (limit raggiunto): {stats}")
                return stats

    stats = {"scanned": scanned, "created": created, "updated": updated}
    if verbose: 
        print(f"[SCRAPER] DONE: {stats}")
    return stats
