from django.contrib import admin
from .models import Inmate, Charge, ChildAbuseIndex, NonChildAbuseIndex, LeaderboardEntry, MurderIndex, NonMurderIndex

@admin.register(Inmate)
class InmateAdmin(admin.ModelAdmin):
    list_display  = ("booking_number", "last_name", "first_name", "age")
    search_fields = ("booking_number", "first_name", "last_name")

@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display  = ("inmate", "charge", "bond_amount", "court_case_number")
    search_fields = ("inmate__booking_number", "inmate__last_name", "charge", "court_case_number")

@admin.register(ChildAbuseIndex)
class ChildAbuseIndexAdmin(admin.ModelAdmin):
    list_display = ("inmate", "created_at")
    search_fields = ("inmate__booking_number", "inmate__last_name")

@admin.register(NonChildAbuseIndex)
class NonChildAbuseIndexAdmin(admin.ModelAdmin):
    list_display = ("inmate", "created_at")
    search_fields = ("inmate__booking_number", "inmate__last_name")

@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display  = ("name", "score", "mode", "created_at")
    list_filter   = ("mode",)
    search_fields = ("name",)

@admin.register(MurderIndex)
class MurderIndexAdmin(admin.ModelAdmin):
    list_display = ("inmate", "created_at")
    search_fields = ("inmate__booking_number", "inmate__last_name")

@admin.register(NonMurderIndex)
class NonMurderIndexAdmin(admin.ModelAdmin):
    list_display = ("inmate", "created_at")
    search_fields = ("inmate__booking_number", "inmate__last_name")