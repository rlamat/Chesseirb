from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils import timezone

User = get_user_model()


class PlayerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    chesscom_elo = models.PositiveIntegerField(null=True, blank=True)
    is_banned = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Profil de {self.user.username}"


class Tournament(models.Model):
    MODE_ADMIN = "admin"
    MODE_PLAYER = "player"
    MODE_CHOICES = [
        (MODE_ADMIN, "Résultats saisis par les admins"),
        (MODE_PLAYER, "Résultats saisis par les joueurs"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_REGISTRATION = "registration"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_REGISTRATION, "Inscriptions ouvertes"),
        (STATUS_RUNNING, "En cours"),
        (STATUS_COMPLETED, "Terminé"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField()
    rounds_planned = models.PositiveIntegerField(default=5)
    mode = models.CharField(
        max_length=20, choices=MODE_CHOICES, default=MODE_ADMIN
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="tournaments_created"
    )
    current_round = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime", "-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_registration_open(self) -> bool:
        return self.status == self.STATUS_REGISTRATION

    @property
    def is_running(self) -> bool:
        return self.status == self.STATUS_RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status == self.STATUS_COMPLETED

    def can_edit_setup(self) -> bool:
        return self.status in {self.STATUS_DRAFT, self.STATUS_REGISTRATION}

    def participants(self):
        return User.objects.filter(registrations__tournament=self, registrations__is_active=True)


class TournamentRegistration(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="registrations", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        User, related_name="registrations", on_delete=models.CASCADE
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("tournament", "user")
        ordering = ["joined_at"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.tournament}"


class Round(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="rounds", on_delete=models.CASCADE
    )
    number = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("tournament", "number")
        ordering = ["number"]

    def __str__(self) -> str:
        return f"Round {self.number} - {self.tournament.name}"

    @property
    def is_complete(self) -> bool:
        pending = self.matches.filter(result=Match.RESULT_PENDING).exists()
        return not pending


class Match(models.Model):
    RESULT_PENDING = "pending"
    RESULT_WHITE = "white"
    RESULT_BLACK = "black"
    RESULT_DRAW = "draw"
    RESULT_BYE = "bye"

    RESULT_CHOICES = [
        (RESULT_PENDING, "En attente"),
        (RESULT_WHITE, "Victoire blancs"),
        (RESULT_BLACK, "Victoire noirs"),
        (RESULT_DRAW, "Nulle"),
        (RESULT_BYE, "Exempt (bye)"),
    ]

    round = models.ForeignKey(
        Round, related_name="matches", on_delete=models.CASCADE
    )
    white_player = models.ForeignKey(
        User, related_name="white_matches", on_delete=models.CASCADE, null=True, blank=True
    )
    black_player = models.ForeignKey(
        User, related_name="black_matches", on_delete=models.CASCADE, null=True, blank=True
    )
    result = models.CharField(
        max_length=20, choices=RESULT_CHOICES, default=RESULT_PENDING
    )
    submitted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="results_submitted"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["round", "id"]

    def __str__(self) -> str:
        return f"Round {self.round.number}: {self.white_player} vs {self.black_player}"

    def involves(self, user: User) -> bool:
        return user and (user == self.white_player or user == self.black_player)

    def points_for(self, user: User) -> float:
        if self.result == self.RESULT_PENDING:
            return 0
        if self.result == self.RESULT_BYE and self.involves(user):
            return 1
        if self.result == self.RESULT_WHITE:
            return 1 if user == self.white_player else 0
        if self.result == self.RESULT_BLACK:
            return 1 if user == self.black_player else 0
        if self.result == self.RESULT_DRAW and self.involves(user):
            return 0.5
        return 0

    @property
    def is_bye(self) -> bool:
        return self.result == self.RESULT_BYE or (self.white_player and not self.black_player)


def color_balance_for_player(tournament: Tournament, user: User) -> Tuple[int, int]:
    whites = Match.objects.filter(
        round__tournament=tournament, white_player=user
    ).count()
    blacks = Match.objects.filter(
        round__tournament=tournament, black_player=user
    ).count()
    return whites, blacks


def points_table(tournament: Tournament) -> Dict[int, float]:
    scores: Dict[int, float] = defaultdict(float)
    matches = Match.objects.filter(round__tournament=tournament).exclude(
        result=Match.RESULT_PENDING
    )
    for match in matches:
        if match.white_player:
            scores[match.white_player_id] += match.points_for(match.white_player)
        if match.black_player:
            scores[match.black_player_id] += match.points_for(match.black_player)
    return scores


def buchholz_scores(tournament: Tournament, scores: Dict[int, float]) -> Dict[int, float]:
    buchholz: Dict[int, float] = defaultdict(float)
    matches = Match.objects.filter(round__tournament=tournament).exclude(
        result=Match.RESULT_PENDING
    )
    for match in matches:
        if match.white_player and match.black_player:
            white_score = scores.get(match.black_player_id, 0)
            black_score = scores.get(match.white_player_id, 0)
            buchholz[match.white_player_id] += white_score
            buchholz[match.black_player_id] += black_score
        elif match.white_player and not match.black_player:
            # bye: add nothing
            buchholz[match.white_player_id] += 0
    return buchholz


def standings_for_tournament(tournament: Tournament) -> List[Dict]:
    regs = TournamentRegistration.objects.filter(
        tournament=tournament, is_active=True
    ).select_related("user")
    scores = points_table(tournament)
    buchholz = buchholz_scores(tournament, scores)
    table = []
    for reg in regs:
        whites, blacks = color_balance_for_player(tournament, reg.user)
        table.append(
            {
                "user": reg.user,
                "score": scores.get(reg.user_id, 0),
                "buchholz": buchholz.get(reg.user_id, 0),
                "whites": whites,
                "blacks": blacks,
                "matches_played": whites + blacks,
            }
        )
    table.sort(
        key=lambda row: (
            -row["score"],
            -row["buchholz"],
            -row["matches_played"],
            row["user"].username.lower(),
        )
    )
    return table
