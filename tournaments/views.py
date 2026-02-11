from datetime import datetime

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import MatchResultForm, ProfileForm, SignUpForm, TournamentForm
from .models import Match, Round, Tournament, TournamentRegistration, standings_for_tournament
from .services import can_generate_next_round, generate_next_round


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_staff)(view_func)


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Bienvenue au club Chesseirb !")
            return redirect("tournament_list_open")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def tournament_list_open(request):
    tournaments = Tournament.objects.filter(
        status=Tournament.STATUS_REGISTRATION
    ).order_by("start_datetime")
    return render(request, "tournaments/open_list.html", {"tournaments": tournaments})


def tournament_list_completed(request):
    tournaments = Tournament.objects.filter(
        status=Tournament.STATUS_COMPLETED
    ).order_by("-start_datetime")
    return render(request, "tournaments/completed_list.html", {"tournaments": tournaments})


@login_required
def profile(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile)

    stats = user_stats(request.user)
    return render(request, "tournaments/profile.html", {"form": form, "stats": stats})


def user_stats(user):
    matches = Match.objects.filter(
        Q(white_player=user) | Q(black_player=user)
    ).exclude(result=Match.RESULT_PENDING)
    wins = matches.filter(
        (Q(result=Match.RESULT_WHITE) & Q(white_player=user))
        | (Q(result=Match.RESULT_BLACK) & Q(black_player=user))
        | Q(result=Match.RESULT_BYE)
    ).count()
    losses = matches.filter(
        (Q(result=Match.RESULT_WHITE) & Q(black_player=user))
        | (Q(result=Match.RESULT_BLACK) & Q(white_player=user))
    ).count()
    draws = matches.filter(result=Match.RESULT_DRAW).count()
    whites_played = matches.filter(white_player=user).count()
    blacks_played = matches.filter(black_player=user).count()
    white_wins = matches.filter(result=Match.RESULT_WHITE, white_player=user).count()
    black_wins = matches.filter(result=Match.RESULT_BLACK, black_player=user).count()
    white_win_rate = (white_wins / whites_played * 100) if whites_played else 0
    black_win_rate = (black_wins / blacks_played * 100) if blacks_played else 0
    defeats = []
    lost_matches = matches.filter(
        (Q(result=Match.RESULT_WHITE) & Q(black_player=user))
        | (Q(result=Match.RESULT_BLACK) & Q(white_player=user))
    )
    for m in lost_matches:
        opponent = m.white_player if m.white_player != user else m.black_player
        if opponent:
            color = "blancs" if m.white_player == user else "noirs"
            defeats.append({"opponent": opponent, "color": color, "round": m.round.number})
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "white_win_rate": round(white_win_rate, 1),
        "black_win_rate": round(black_win_rate, 1),
        "whites_played": whites_played,
        "blacks_played": blacks_played,
        "defeats": defeats,
    }


def tournament_detail(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    registrations = TournamentRegistration.objects.filter(
        tournament=tournament, is_active=True
    ).select_related("user")
    user_registration = None
    if request.user.is_authenticated:
        user_registration = registrations.filter(user=request.user).first()

    standings = standings_for_tournament(tournament)
    rounds = (
        tournament.rounds.prefetch_related(
            "matches__white_player", "matches__black_player"
        ).all()
    )
    can_report = tournament.mode == Tournament.MODE_PLAYER

    return render(
        request,
        "tournaments/detail.html",
        {
            "tournament": tournament,
            "registrations": registrations,
            "user_registration": user_registration,
            "standings": standings,
            "rounds": rounds,
            "can_report": can_report,
        },
    )


@login_required
def register_to_tournament(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    if request.user.profile.is_banned:
        messages.error(request, "Votre compte est banni des inscriptions aux tournois.")
        return redirect("tournament_detail", pk=pk)
    if not tournament.is_registration_open:
        messages.error(request, "Les inscriptions ne sont pas ouvertes.")
        return redirect("tournament_detail", pk=pk)
    reg, created = TournamentRegistration.objects.get_or_create(
        tournament=tournament, user=request.user
    )
    reg.is_active = True
    reg.save()
    messages.success(request, "Inscription enregistrée.")
    return redirect("tournament_detail", pk=pk)


@login_required
def unregister_from_tournament(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    if tournament.status != Tournament.STATUS_REGISTRATION:
        messages.error(request, "Vous ne pouvez plus vous désinscrire.")
        return redirect("tournament_detail", pk=pk)
    TournamentRegistration.objects.filter(
        tournament=tournament, user=request.user
    ).update(is_active=False)
    messages.info(request, "Vous êtes désinscrit du tournoi.")
    return redirect("tournament_detail", pk=pk)


@staff_required
def create_tournament(request):
    if request.method == "POST":
        form = TournamentForm(request.POST)
        if form.is_valid():
            tournament = form.save(commit=False)
            tournament.created_by = request.user
            tournament.save()
            messages.success(request, "Tournoi créé.")
            return redirect("tournament_detail", pk=tournament.pk)
    else:
        form = TournamentForm(initial={"status": Tournament.STATUS_DRAFT})
    return render(request, "tournaments/tournament_form.html", {"form": form})


@staff_required
def edit_tournament(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    if not tournament.can_edit_setup():
        messages.error(request, "Ce tournoi ne peut plus être modifié.")
        return redirect("tournament_detail", pk=pk)
    if request.method == "POST":
        form = TournamentForm(request.POST, instance=tournament)
        if form.is_valid():
            form.save()
            messages.success(request, "Tournoi mis à jour.")
            return redirect("tournament_detail", pk=pk)
    else:
        form = TournamentForm(instance=tournament)
    return render(
        request, "tournaments/tournament_form.html", {"form": form, "tournament": tournament}
    )


@staff_required
def open_registration(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    tournament.status = Tournament.STATUS_REGISTRATION
    tournament.save(update_fields=["status"])
    messages.success(request, "Inscriptions ouvertes.")
    return redirect("tournament_detail", pk=pk)


@staff_required
def close_registration(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    tournament.status = Tournament.STATUS_DRAFT
    tournament.save(update_fields=["status"])
    messages.info(request, "Inscriptions fermées.")
    return redirect("tournament_detail", pk=pk)


@staff_required
def start_tournament(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    if tournament.status not in [Tournament.STATUS_REGISTRATION, Tournament.STATUS_DRAFT]:
        messages.error(request, "Le tournoi est déjà lancé.")
        return redirect("tournament_detail", pk=pk)
    tournament.status = Tournament.STATUS_RUNNING
    tournament.save(update_fields=["status"])
    generate_next_round(tournament)
    messages.success(request, "Tournoi lancé, appariements du round 1 générés.")
    return redirect("tournament_detail", pk=pk)


@staff_required
def advance_round(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    try:
        generate_next_round(tournament)
        messages.success(request, "Nouveaux appariements générés.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("tournament_detail", pk=pk)


@staff_required
def complete_tournament(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    last_round = tournament.rounds.filter(number=tournament.current_round).first()
    if last_round and last_round.matches.filter(result=Match.RESULT_PENDING).exists():
        messages.error(request, "Terminez d'abord tous les matchs.")
        return redirect("tournament_detail", pk=pk)
    tournament.status = Tournament.STATUS_COMPLETED
    tournament.save(update_fields=["status"])
    messages.success(request, "Tournoi marqué comme terminé.")
    return redirect("tournament_detail", pk=pk)


def can_submit_result(tournament, match, user):
    if match.is_bye:
        return False
    if tournament.mode == Tournament.MODE_ADMIN:
        return user.is_staff
    return user.is_staff or match.involves(user)


@staff_required
def admin_users(request):
    from django.core.paginator import Paginator

    from django.contrib.auth import get_user_model

    User = get_user_model()
    query = (request.GET.get("q") or "").strip()
    users = User.objects.filter(last_login__isnull=False).select_related("profile")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    users = users.order_by("username")

    paginator = Paginator(users, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")
        target = get_object_or_404(User, pk=user_id)
        if target == request.user:
            messages.error(request, "Vous ne pouvez pas agir sur votre propre compte ici.")
            return redirect("admin_users")

        if action == "ban":
            target.profile.is_banned = True
            target.profile.save(update_fields=["is_banned"])
            messages.info(request, f"{target.username} a été banni des inscriptions.")
        elif action == "unban":
            target.profile.is_banned = False
            target.profile.save(update_fields=["is_banned"])
            messages.success(request, f"{target.username} est débanni.")
        elif action == "promote":
            target.is_staff = True
            target.is_superuser = True
            target.save(update_fields=["is_staff", "is_superuser"])
            messages.success(request, f"{target.username} est désormais administrateur.")
        elif action == "demote":
            target.is_staff = False
            target.is_superuser = False
            target.save(update_fields=["is_staff", "is_superuser"])
            messages.info(request, f"Les droits admin de {target.username} ont été retirés.")
        elif action == "delete":
            target.delete()
            messages.warning(request, "Compte supprimé.")
        else:
            messages.error(request, "Action inconnue.")
        return redirect("admin_users")

    return render(
        request,
        "tournaments/admin_users.html",
        {
            "page_obj": page_obj,
            "query": query,
        },
    )

@login_required
def user_search(request):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    query = (request.GET.get("q") or "").strip()
    users = User.objects.filter(last_login__isnull=False)
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    users = users.order_by("username")
    return render(
        request,
        "tournaments/user_search.html",
        {"users": users, "query": query},
    )


@login_required
def user_detail(request, user_id):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile"), pk=user_id, last_login__isnull=False)
    stats = user_stats(user)
    return render(
        request,
        "tournaments/user_detail.html",
        {"target_user": user, "stats": stats},
    )


@login_required
def submit_result(request, pk, match_id):
    tournament = get_object_or_404(Tournament, pk=pk)
    match = get_object_or_404(Match, pk=match_id, round__tournament=tournament)
    if not can_submit_result(tournament, match, request.user):
        return HttpResponseForbidden("Vous ne pouvez pas saisir ce résultat.")

    if request.method == "POST":
        form = MatchResultForm(request.POST, instance=match)
        if form.is_valid():
            result_match = form.save(commit=False)
            result_match.submitted_by = request.user
            result_match.save()
            # Close round end time if complete
            rnd = match.round
            if rnd.matches.filter(result=Match.RESULT_PENDING).count() == 0:
                rnd.ended_at = timezone.now()
                rnd.save(update_fields=["ended_at"])
                # Auto-génération du round suivant si possible
                if (
                    tournament.status == Tournament.STATUS_RUNNING
                    and tournament.current_round == rnd.number
                    and tournament.current_round < tournament.rounds_planned
                ):
                    try:
                        generate_next_round(tournament)
                        messages.success(
                            request,
                            f"Round {rnd.number} terminé. Appariements du round {tournament.current_round} générés.",
                        )
                    except ValueError:
                        pass
            messages.success(request, "Résultat enregistré.")
            return redirect("tournament_detail", pk=pk)
    else:
        form = MatchResultForm(instance=match)
    return render(
        request,
        "tournaments/submit_result.html",
        {"form": form, "match": match, "tournament": tournament},
    )
