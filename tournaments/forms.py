from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import Match, PlayerProfile, Tournament

User = get_user_model()


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email")


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = (
            "name",
            "description",
            "start_datetime",
            "rounds_planned",
            "mode",
            "status",
        )
        widgets = {
            "start_datetime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = PlayerProfile
        fields = ("chesscom_elo",)


class MatchResultForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ("result",)
        widgets = {
            "result": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide states that users shouldn't pick manually
        self.fields["result"].choices = [
            (code, label)
            for code, label in Match.RESULT_CHOICES
            if code not in (Match.RESULT_PENDING, Match.RESULT_BYE)
        ]
