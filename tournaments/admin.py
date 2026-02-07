from django.contrib import admin

from .models import Match, PlayerProfile, Round, Tournament, TournamentRegistration


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "mode", "start_datetime", "rounds_planned", "current_round")
    list_filter = ("status", "mode")
    search_fields = ("name",)


@admin.register(TournamentRegistration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "tournament", "is_active", "joined_at")
    list_filter = ("is_active",)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("tournament", "number", "started_at", "ended_at")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("round", "white_player", "black_player", "result", "updated_at")
    list_filter = ("result",)


@admin.register(PlayerProfile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "chesscom_elo")
