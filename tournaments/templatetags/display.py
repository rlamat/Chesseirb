from django import template

register = template.Library()


@register.filter
def user_with_elo(user):
    if not user:
        return ""
    elo = getattr(getattr(user, "profile", None), "chesscom_elo", None)
    if elo:
        return f"{user.username} ({elo})"
    return user.username
