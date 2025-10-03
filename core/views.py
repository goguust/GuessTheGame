from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required  # IMPORTANTISSIMO
from core.models import Inmate, Charge, ChildAbuseIndex, NonChildAbuseIndex, LeaderboardEntry, MurderIndex, NonMurderIndex, CannabisIndex, CocaineFentanylIndex
from core.services.scraper import run_scrape
import random
from django.db.models import Q
import string

def home(request):
    """Pagina iniziale con i pulsanti/modalità."""
    return render(request, "core/home.html")


@staff_member_required
def update_db(request):
    if request.method != "POST":
        return redirect("home")

    raw_limit = request.POST.get("limit")
    limit = None
    try:
        if raw_limit and raw_limit != "":
            val = int(raw_limit)
            limit = None if val == 0 else max(val, 1)
    except ValueError:
        limit = None

    raw_filters = request.POST.get("filters", "").strip().lower()

    filters = None
    if not raw_filters:
        # caso vuoto → tutte le lettere
        filters = list(string.ascii_lowercase)
    elif len(raw_filters) == 1 and raw_filters.isalpha():
        # una lettera → da quella alla z
        start = raw_filters
        letters = string.ascii_lowercase
        idx = letters.index(start)
        filters = list(letters[idx:])
    else:
        # più lettere → prendi solo quelle valide
        filters = list({c for c in raw_filters if c.isalpha()})

    stats = run_scrape(filters=filters, limit=limit, reset=True, verbose=True)
    messages.success(request, f"DB aggiornato: scanned={stats['scanned']}, created={stats['created']}, updated={stats['updated']}")
    return redirect("home")


def game_mode_1(request):
    """Mostra due Inmate casuali con foto e nome."""
    qs = Inmate.objects.exclude(image__isnull=True).exclude(image="")
    count = qs.count()
    if count < 2:
        return render(request, "core/game1_empty.html", {"count": count})

    ids = list(qs.values_list("id", flat=True))
    a_id, b_id = random.sample(ids, 2)
    a = Inmate.objects.get(id=a_id)
    b = Inmate.objects.get(id=b_id)

    if request.method == "POST":
        # se vuoi registrare la scelta, fallo qui
        return redirect("game1")

    return render(request, "core/game1.html", {"a": a, "b": b})

@staff_member_required
def run_filters(request):
    if request.method != "POST":
        return redirect("home")

    # Se il DB è vuoto, evita errori e informa l'utente
    if Inmate.objects.count() == 0:
        messages.info(request, "Database vuoto: premi prima 'Aggiorna database', poi 'Filtra'.")
        return redirect("home")

    # Svuota gli indici
    ChildAbuseIndex.objects.all().delete()
    NonChildAbuseIndex.objects.all().delete()

    # Regole: nello STESSO charge devono comparire 'child' e una delle keyword
    secondary_keywords = [
        "assault", "sex", "sexual", "abuse", "molest", "exploitation",
        "pornograph", "indecent", "lewd", "lascivious", "battery",
        "neglect", "endangerment", "solicitation", "entice", "incest",
        "rape", "sodomy", "traffick", "conduct", "exposure", "fondling",
        "statutory", "child abuse", "child neglect", "child porn", "video"
    ]

    second_q = Q()
    for kw in secondary_keywords:
        second_q |= Q(charge__icontains=kw)

    # Charges che contengono 'child' E almeno una delle keyword sopra
    matching = Charge.objects.filter(
        Q(charge__icontains="child") & second_q
    ).values_list("inmate_id", flat=True).distinct()

    child_inmate_ids = set(matching)

    # Popola indici
    child_inmates = Inmate.objects.filter(id__in=child_inmate_ids)
    non_child_inmates = Inmate.objects.exclude(id__in=child_inmate_ids)

    ChildAbuseIndex.objects.bulk_create(
        [ChildAbuseIndex(inmate=i) for i in child_inmates],
        ignore_conflicts=True,
    )
    NonChildAbuseIndex.objects.bulk_create(
        [NonChildAbuseIndex(inmate=i) for i in non_child_inmates],
        ignore_conflicts=True,
    )

    messages.success(
        request,
        f"Filtri applicati: child_abuse={child_inmates.count()}, non_child={non_child_inmates.count()}"
    )
    return redirect("home")
    
def _child_mode_reset_session(request):
    request.session["lives"] = 3
    request.session["streak"] = 0
    request.session["score"] = 0
    request.session["mult"] = 1
    request.session["seen_child_ids"] = []
    request.session["seen_non_child_ids"] = []
    request.session.pop("current_pair", None)
    request.session.modified = True


def _calc_multiplier(streak: int) -> int:
    if streak >= 15:
        return 10
    if streak >= 10:
        return 4
    if streak >= 5:
        return 2
    return 1


def _pick_pair(request):
    """Restituisce (child_obj, non_obj) mai visti in questa sessione, o (None,None) se non disponibili."""
    seen_child = set(request.session.get("seen_child_ids", []))
    seen_non = set(request.session.get("seen_non_child_ids", []))

    child_qs = Inmate.objects.filter(idx_child_abuse__isnull=False).exclude(image__isnull=True).exclude(image="")
    non_qs   = Inmate.objects.filter(idx_non_child_abuse__isnull=False).exclude(image__isnull=True).exclude(image="")

    child_ids = list(child_qs.values_list("id", flat=True))
    non_ids   = list(non_qs.values_list("id", flat=True))

    avail_child = [i for i in child_ids if i not in seen_child]
    avail_non   = [i for i in non_ids if i not in seen_non]

    if not avail_child or not avail_non:
        return None, None

    child_id = random.choice(avail_child)
    non_id   = random.choice(avail_non)

    child = Inmate.objects.get(id=child_id)
    non   = Inmate.objects.get(id=non_id)
    return child, non


def child_mode_start(request):
    """Reset e primo round."""
    _child_mode_reset_session(request)
    return redirect("child_mode_play")


def child_mode_play(request):
    """Render del round corrente con due foto random (1 child vs 1 non-child)."""
    child, non = _pick_pair(request)
    if not child or not non:
        # niente più coppie disponibili
        return redirect("child_mode_gameover")

    # decidi lato a caso
    left_is_child = random.choice([True, False])
    left  = child if left_is_child else non
    right = non if left_is_child else child

    # salva pair corrente in sessione
    request.session["current_pair"] = {
        "left_id": left.id,
        "right_id": right.id,
        "child_id": child.id,
        "non_id": non.id,
        "left_is_child": left_is_child,
    }
    # aggiorna "seen"
    seen_child = set(request.session.get("seen_child_ids", []))
    seen_non   = set(request.session.get("seen_non_child_ids", []))
    seen_child.add(child.id)
    seen_non.add(non.id)
    request.session["seen_child_ids"] = list(seen_child)
    request.session["seen_non_child_ids"] = list(seen_non)
    request.session.modified = True

    ctx = {
        "left": left,
        "right": right,
        "lives": request.session["lives"],
        "streak": request.session["streak"],
        "score": request.session["score"],
        "mult": request.session["mult"],
    }
    return render(request, "core/child_mode_play.html", ctx)


def child_mode_choose(request):
    """Gestisce la scelta utente (POST con valore 'side' = 'left'/'right')."""
    if request.method != "POST":
        return redirect("child_mode_play")

    pair = request.session.get("current_pair")
    if not pair:
        return redirect("child_mode_play")

    side = request.POST.get("side")  # "left" o "right"
    is_correct = (side == "left" and pair["left_is_child"]) or (side == "right" and not pair["left_is_child"] == True)

    # NB: più chiaro:
    # if side == "left":
    #     is_correct = pair["left_is_child"]
    # else:
    #     is_correct = not pair["left_is_child"]

    # stato
    lives  = request.session.get("lives", 3)
    streak = request.session.get("streak", 0)
    score  = request.session.get("score", 0)

    if side == "left":
        is_correct = pair["left_is_child"]
    else:
        is_correct = not pair["left_is_child"]

    if is_correct:
        streak += 1
        mult = _calc_multiplier(streak)
        score += 1 * mult
        # vita bonus a ogni multiplo di 5, max 5
        if streak % 5 == 0 and lives < 5:
            lives += 1
    else:
        lives -= 1
        if lives < 0:
            lives = 0
        streak = 0

    # aggiorna mult dopo l'aggiornamento streak
    mult = _calc_multiplier(streak)

    request.session["lives"] = lives
    request.session["streak"] = streak
    request.session["score"] = score
    request.session["mult"] = mult
    request.session.modified = True

    if lives == 0:
        return redirect("child_mode_gameover")

    # prossimo round
    return redirect("child_mode_play")


def child_mode_gameover(request):
    """Schermata di 'morte' con form per inserire nome (facoltativo)."""
    score = request.session.get("score", 0)
    request.session["final_score"] = score   # <-- salva in sessione
    request.session["mode"] = "child"        # <-- salva modalità corrente
    request.session.modified = True
    print("[DEBUG] GAMEOVER CHILD:", score)   # <-- debug
    return render(request, "core/child_mode_gameover.html", {"final_score": score})


def leaderboard(request, mode="child"):
    if mode not in ("child", "murder", "drugs"):
        mode = "child"
    entries = LeaderboardEntry.objects.filter(mode=mode)[:50]
    return render(request, "core/leaderboard.html", {"entries": entries, "mode": mode})



def leaderboard_submit(request):
    if request.method == "POST":
        print("[DEBUG] leaderboard_submit CALLED")
        print("POST:", request.POST)
        print("SESSION:", dict(request.session))

        name = request.POST.get("name", "").strip()
        score = request.session.get("final_score", 0)
        mode = request.session.get("mode", "child")

        print(f"[DEBUG] name={name}, score={score}, mode={mode}")

        if score > 0:
            LeaderboardEntry.objects.create(
                name=name if name else "Anonimo",
                score=score,
                mode=mode
            )
            print("[DEBUG] Entry salvata!")

        return redirect("leaderboard", mode=mode)

    return redirect("home")

    
@staff_member_required
def run_filters_murder(request):
    if request.method != "POST":
        return redirect("home")

    if Inmate.objects.count() == 0:
        messages.info(request, "Database vuoto: premi prima 'Aggiorna database', poi 'Filtra Murder'.")
        return redirect("home")

    MurderIndex.objects.all().delete()
    NonMurderIndex.objects.all().delete()

    # “murder” in almeno un charge (case-insensitive)
    murder_ids = set(
        Charge.objects.filter(charge__icontains="murder")
        .values_list("inmate_id", flat=True)
        .distinct()
    )

    murder_inmates = Inmate.objects.filter(id__in=murder_ids)
    non_murder_inmates = Inmate.objects.exclude(id__in=murder_ids)

    MurderIndex.objects.bulk_create([MurderIndex(inmate=i) for i in murder_inmates], ignore_conflicts=True)
    NonMurderIndex.objects.bulk_create([NonMurderIndex(inmate=i) for i in non_murder_inmates], ignore_conflicts=True)

    messages.success(
        request,
        f"Filtri Murder applicati: murder={murder_inmates.count()}, non_murder={non_murder_inmates.count()}"
    )
    return redirect("home")

# ---------- Modalità Murder vs Non-Murder ----------

def _murder_reset_session(request):
    request.session["m_lives"] = 3
    request.session["m_streak"] = 0
    request.session["m_score"] = 0
    request.session["m_mult"] = 1
    request.session["m_seen_murder_ids"] = []
    request.session["m_seen_non_murder_ids"] = []
    request.session.pop("m_current_pair", None)
    request.session.modified = True

def _murder_calc_multiplier(streak:int)->int:
    if streak >= 15: return 10
    if streak >= 10: return 4
    if streak >= 5:  return 2
    return 1

def _murder_pick_pair(request):
    seen_m = set(request.session.get("m_seen_murder_ids", []))
    seen_n = set(request.session.get("m_seen_non_murder_ids", []))

    m_qs = Inmate.objects.filter(idx_murder__isnull=False).exclude(image__isnull=True).exclude(image="")
    n_qs = Inmate.objects.filter(idx_non_murder__isnull=False).exclude(image__isnull=True).exclude(image="")

    m_ids = [i for i in m_qs.values_list("id", flat=True) if i not in seen_m]
    n_ids = [i for i in n_qs.values_list("id", flat=True) if i not in seen_n]
    if not m_ids or not n_ids:
        return None, None
    import random
    m_id = random.choice(m_ids); n_id = random.choice(n_ids)
    return Inmate.objects.get(id=m_id), Inmate.objects.get(id=n_id)

def murder_mode_start(request):
    _murder_reset_session(request)
    return redirect("murder_mode_play")

def murder_mode_play(request):
    import random
    m, n = _murder_pick_pair(request)
    if not m or not n:
        # riusa la stessa pagina "empty" della child-mode
        c = Inmate.objects.filter(idx_murder__isnull=False).exclude(image__isnull=True).exclude(image="").count()
        d = Inmate.objects.filter(idx_non_murder__isnull=False).exclude(image__isnull=True).exclude(image="").count()
        return render(request, "core/murder_mode_empty.html", {"murder_count": c, "non_murder_count": d})

    left_is_murder = random.choice([True, False])
    left  = m if left_is_murder else n
    right = n if left_is_murder else m

    # salva sessione
    request.session["m_current_pair"] = {
        "left_id": left.id, "right_id": right.id,
        "murder_id": m.id, "non_id": n.id,
        "left_is_murder": left_is_murder,
    }
    sm = set(request.session.get("m_seen_murder_ids", [])); sm.add(m.id)
    sn = set(request.session.get("m_seen_non_murder_ids", [])); sn.add(n.id)
    request.session["m_seen_murder_ids"] = list(sm)
    request.session["m_seen_non_murder_ids"] = list(sn)
    request.session.modified = True

    ctx = {
        "left": left, "right": right,
        "lives": request.session["m_lives"],
        "streak": request.session["m_streak"],
        "score": request.session["m_score"],
        "mult": request.session["m_mult"],
    }
    return render(request, "core/murder_mode_play.html", ctx)

def murder_mode_choose(request):
    if request.method != "POST":
        return redirect("murder_mode_play")
    pair = request.session.get("m_current_pair")
    if not pair:
        return redirect("murder_mode_play")
    side = request.POST.get("side")
    is_correct = (side == "left" and pair["left_is_murder"]) or (side == "right" and not pair["left_is_murder"])

    lives  = request.session.get("m_lives", 3)
    streak = request.session.get("m_streak", 0)
    score  = request.session.get("m_score", 0)

    if is_correct:
        streak += 1
        mult = _murder_calc_multiplier(streak)
        score += 1 * mult
        if streak % 5 == 0 and lives < 5:
            lives += 1
    else:
        lives = max(lives - 1, 0)
        streak = 0

    mult = _murder_calc_multiplier(streak)
    request.session["m_lives"] = lives
    request.session["m_streak"] = streak
    request.session["m_score"] = score
    request.session["m_mult"] = mult
    request.session.modified = True

    if lives == 0:
        return redirect("murder_mode_gameover")
    return redirect("murder_mode_play")

def murder_mode_gameover(request):
    score = request.session.get("m_score", 0)
    request.session["final_score"] = score   # <-- salva in sessione
    request.session["mode"] = "murder"       # <-- salva modalità corrente
    return render(request, "core/murder_mode_gameover.html", {"final_score": score})

def game_over(request, mode):
    score = request.session.get("score", 0)
    request.session["final_score"] = score
    request.session["mode"] = mode
    return render(request, "core/game_over.html", {"score": score, "mode": mode})

@staff_member_required
def run_filters_drugs(request):
    """Filtra cannabis vs cocaine/fentanyl"""
    if request.method != "POST":
        return redirect("home")

    if Inmate.objects.count() == 0:
        messages.info(request, "Database vuoto: premi prima 'Aggiorna database', poi 'Filtra Drugs'.")
        return redirect("home")

    # reset
    CannabisIndex.objects.all().delete()
    CocaineFentanylIndex.objects.all().delete()

    # Cannabis
    cannabis_ids = set(
        Charge.objects.filter(charge__icontains="cannabis")
        .values_list("inmate_id", flat=True)
    )
    # Cocaine o Fentanyl
    cocaine_ids = set(
        Charge.objects.filter(
            Q(charge__icontains="cocaine") | Q(charge__icontains="fentanyl")
        ).values_list("inmate_id", flat=True)
    )

    cannabis_inmates = Inmate.objects.filter(id__in=cannabis_ids)
    cocaine_inmates  = Inmate.objects.filter(id__in=cocaine_ids)

    CannabisIndex.objects.bulk_create([CannabisIndex(inmate=i) for i in cannabis_inmates], ignore_conflicts=True)
    CocaineFentanylIndex.objects.bulk_create([CocaineFentanylIndex(inmate=i) for i in cocaine_inmates], ignore_conflicts=True)

    messages.success(
        request,
        f"Filtri Drugs applicati: cannabis={cannabis_inmates.count()}, cocaine/fentanyl={cocaine_inmates.count()}"
    )
    return redirect("home")

def _drugs_reset_session(request):
    request.session["d_lives"] = 3
    request.session["d_streak"] = 0
    request.session["d_score"] = 0
    request.session["d_mult"] = 1
    request.session["d_seen_cannabis"] = []
    request.session["d_seen_cocaine"] = []
    request.session.pop("d_current_pair", None)
    request.session.modified = True

def _drugs_calc_multiplier(streak:int)->int:
    if streak >= 15: return 10
    if streak >= 10: return 4
    if streak >= 5:  return 2
    return 1

def _drugs_pick_pair(request):
    seen_c = set(request.session.get("d_seen_cannabis", []))
    seen_cf = set(request.session.get("d_seen_cocaine", []))

    c_qs  = Inmate.objects.filter(idx_cannabis__isnull=False).exclude(image__isnull=True).exclude(image="")
    cf_qs = Inmate.objects.filter(idx_cocaine_fentanyl__isnull=False).exclude(image__isnull=True).exclude(image="")

    c_ids  = [i for i in c_qs.values_list("id", flat=True) if i not in seen_c]
    cf_ids = [i for i in cf_qs.values_list("id", flat=True) if i not in seen_cf]

    if not c_ids or not cf_ids:
        return None, None

    import random
    c_id = random.choice(c_ids)
    cf_id = random.choice(cf_ids)
    return Inmate.objects.get(id=c_id), Inmate.objects.get(id=cf_id)

def drugs_mode_start(request):
    _drugs_reset_session(request)
    return redirect("drugs_mode_play")

def drugs_mode_play(request):
    import random
    c, cf = _drugs_pick_pair(request)
    if not c or not cf:
        return render(request, "core/drugs_mode_empty.html")

    left_is_cannabis = random.choice([True, False])
    left  = c if left_is_cannabis else cf
    right = cf if left_is_cannabis else c

    request.session["d_current_pair"] = {
        "left_id": left.id, "right_id": right.id,
        "cannabis_id": c.id, "cocaine_id": cf.id,
        "left_is_cannabis": left_is_cannabis,
    }
    sc = set(request.session.get("d_seen_cannabis", [])); sc.add(c.id)
    scf = set(request.session.get("d_seen_cocaine", [])); scf.add(cf.id)
    request.session["d_seen_cannabis"] = list(sc)
    request.session["d_seen_cocaine"] = list(scf)
    request.session.modified = True

    ctx = {
        "left": left, "right": right,
        "lives": request.session["d_lives"],
        "streak": request.session["d_streak"],
        "score": request.session["d_score"],
        "mult": request.session["d_mult"],
    }
    return render(request, "core/drugs_mode_play.html", ctx)

def drugs_mode_choose(request):
    if request.method != "POST":
        return redirect("drugs_mode_play")
    pair = request.session.get("d_current_pair")
    if not pair: return redirect("drugs_mode_play")

    side = request.POST.get("side")
    is_correct = (side == "left" and pair["left_is_cannabis"]) or (side == "right" and not pair["left_is_cannabis"])

    lives  = request.session.get("d_lives", 3)
    streak = request.session.get("d_streak", 0)
    score  = request.session.get("d_score", 0)

    if is_correct:
        streak += 1
        mult = _drugs_calc_multiplier(streak)
        score += 1 * mult
        if streak % 5 == 0 and lives < 5:
            lives += 1
    else:
        lives = max(lives - 1, 0)
        streak = 0

    mult = _drugs_calc_multiplier(streak)
    request.session["d_lives"] = lives
    request.session["d_streak"] = streak
    request.session["d_score"] = score
    request.session["d_mult"] = mult
    request.session.modified = True

    if lives == 0:
        return redirect("drugs_mode_gameover")
    return redirect("drugs_mode_play")

def drugs_mode_gameover(request):
    score = request.session.get("d_score", 0)
    request.session["final_score"] = score
    request.session["mode"] = "drugs"
    request.session.modified = True
    return render(request, "core/drugs_mode_gameover.html", {"final_score": score})