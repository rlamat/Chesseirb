import random
from typing import List, Tuple

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import (
    Match,
    Round,
    Tournament,
    TournamentRegistration,
    color_balance_for_player,
    standings_for_tournament,
)

User = get_user_model()


def _sorted_players_for_round(tournament: Tournament) -> List[User]:
    table = standings_for_tournament(tournament)
    table.sort(
        key=lambda row: (
            -row["score"],
            -row["buchholz"],
            row["user"].username.lower(),
        )
    )
    return [row["user"] for row in table]


def _choose_colors(
    tournament: Tournament, p1: User, p2: User
) -> Tuple[User, User]:
    w1, b1 = color_balance_for_player(tournament, p1)
    w2, b2 = color_balance_for_player(tournament, p2)
    diff1 = w1 - b1
    diff2 = w2 - b2
    # Assign colors to reduce imbalance
    if diff1 > diff2:
        return p2, p1  # p2 as white
    if diff2 > diff1:
        return p1, p2
    # If perfectly balanced, alternate by username for determinism
    if p1.username < p2.username:
        return p1, p2
    return p2, p1


def can_generate_next_round(tournament: Tournament) -> bool:
    if tournament.status != Tournament.STATUS_RUNNING:
        return False
    if tournament.current_round == 0:
        return True
    last_round = tournament.rounds.filter(number=tournament.current_round).first()
    if last_round and last_round.matches.filter(result=Match.RESULT_PENDING).exists():
        return False
    return tournament.current_round < tournament.rounds_planned


@transaction.atomic
def generate_next_round(tournament: Tournament) -> Round:
    if not can_generate_next_round(tournament):
        raise ValueError("Les conditions pour générer un round ne sont pas remplies.")

    next_number = tournament.current_round + 1
    round_obj, _ = Round.objects.get_or_create(
        tournament=tournament, number=next_number
    )

    registrations = list(
        TournamentRegistration.objects.filter(
            tournament=tournament, is_active=True
        ).select_related("user")
    )
    players = [r.user for r in registrations]

    if next_number == 1:
        random.shuffle(players)
    else:
        players = _sorted_players_for_round(tournament)

    pairings: List[Tuple[User, User]] = []
    while len(players) >= 2:
        p1 = players.pop(0)
        p2 = players.pop(0)
        pairings.append(_choose_colors(tournament, p1, p2))
    bye_player = players[0] if players else None

    for white, black in pairings:
        Match.objects.create(round=round_obj, white_player=white, black_player=black)
    if bye_player:
        Match.objects.create(
            round=round_obj,
            white_player=bye_player,
            black_player=None,
            result=Match.RESULT_BYE,
        )

    tournament.current_round = next_number
    tournament.save(update_fields=["current_round"])
    return round_obj
