from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),

    path("update-db/", views.update_db, name="update_db"),
    path("run-filters/", views.run_filters, name="run_filters"),
    path("run-filters-murder/", views.run_filters_murder, name="run_filters_murder"),

    # nuova modalità
    path("mode/child/", views.child_mode_start, name="child_mode_start"),
    path("mode/child/play/", views.child_mode_play, name="child_mode_play"),
    path("mode/child/choose/", views.child_mode_choose, name="child_mode_choose"),
    path("mode/child/gameover/", views.child_mode_gameover, name="child_mode_gameover"),
    path("leaderboard/submit/", views.leaderboard_submit, name="leaderboard_submit"),
    path("leaderboard/<str:mode>/", views.leaderboard, name="leaderboard"),
    path("leaderboard/", views.leaderboard, {"mode": "child"}, name="leaderboard_default"),

    
    # modalità murder
    path("mode/murder/", views.murder_mode_start, name="murder_mode_start"),
    path("mode/murder/play/", views.murder_mode_play, name="murder_mode_play"),
    path("mode/murder/choose/", views.murder_mode_choose, name="murder_mode_choose"),
    path("mode/murder/gameover/", views.murder_mode_gameover, name="murder_mode_gameover"),

    # Modalità drugs
    path("mode/drugs/", views.drugs_mode_start, name="drugs_mode_start"),
    path("mode/drugs/play/", views.drugs_mode_play, name="drugs_mode_play"),
    path("mode/drugs/choose/", views.drugs_mode_choose, name="drugs_mode_choose"),
    path("mode/drugs/gameover/", views.drugs_mode_gameover, name="drugs_mode_gameover"),
    path("run-filters-drugs/", views.run_filters_drugs, name="run_filters_drugs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
