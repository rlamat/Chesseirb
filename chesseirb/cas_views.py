import logging
from typing import Any, Dict
from urllib.parse import urlencode
import base64

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def _get_next_url(request):
    default = reverse("tournament_list_open")
    candidate = request.GET.get("next") or request.POST.get("next")
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts=None):
        return candidate
    return default


def _build_service_url(request, next_url: str) -> str:
    """
    CAS requires the service URL passed to /login to match exactly the one
    passed later to /serviceValidate. We include the desired redirect in a
    query param so we can restore it after validation.
    """
    # Callback on our app (where we expect the ticket)
    if settings.CAS_SERVICE_BASE:
        callback = settings.CAS_SERVICE_BASE.rstrip("/") + reverse("cas_callback")
    else:
        callback = request.build_absolute_uri(reverse("cas_callback"))
    callback_with_next = f"{callback}?{urlencode({'next': next_url})}"

    # If a proxy base is defined and authorized, build the proxied service
    if getattr(settings, "CAS_PROXY_BASE", None):
        token_param = getattr(settings, "CAS_PROXY_TOKEN_PARAM", "token")
        # Use standard base64 (not urlsafe) to match the JS example (btoa).
        token = base64.b64encode(callback_with_next.encode()).decode()
        return f"{settings.CAS_PROXY_BASE.rstrip('/')}/?{urlencode({token_param: token})}"

    # Otherwise use the callback directly (requires CAS to authorize the domain)
    return callback_with_next


def cas_login(request):
    """
    Redirects the user to the Bordeaux INP CAS login page with a service URL
    that points back to this project.
    """
    next_url = _get_next_url(request)
    service_url = _build_service_url(request, next_url)
    logger.info("CAS login redirect with service=%s next=%s", service_url, next_url)
    cas_login_url = f"{settings.CAS_SERVER_URL}/login?{urlencode({'service': service_url})}"
    return redirect(cas_login_url)


@csrf_exempt  # CAS performs a GET with external origin; no CSRF token available.
def cas_callback(request):
    """
    Receives the CAS ticket, validates it against /serviceValidate, logs the user
    in (creating the account if needed), then redirects to the requested page.
    """
    ticket = request.GET.get("ticket")
    next_url = _get_next_url(request)
    service_url = _build_service_url(request, next_url)

    if not ticket:
        messages.error(request, "Ticket CAS manquant.")
        return redirect("login")

    try:
        resp = requests.get(
            settings.CAS_VALIDATE_ENDPOINT,
            params={"service": service_url, "ticket": ticket, "format": "json"},
            timeout=5,
        )
    except requests.RequestException as exc:
        logger.exception("CAS validation request failed")
        messages.error(request, f"Erreur de connexion au CAS: {exc}")
        return redirect("login")

    if resp.status_code != 200:
        messages.error(request, f"Validation CAS échouée (HTTP {resp.status_code}).")
        return redirect("login")

    data: Dict[str, Any] = resp.json()
    auth = data.get("serviceResponse", {}).get("authenticationSuccess")
    if not auth:
        messages.error(request, "Ticket CAS invalide.")
        return redirect("login")

    attrs = auth.get("attributes", {})

    def first_value(key, fallback=None):
        val = attrs.get(key, fallback)
        if isinstance(val, list):
            return val[0] if val else fallback
        return val

    username = first_value("uid", auth.get("user"))
    email = first_value("courriel", "")
    first_name = first_value("prenom", "")
    last_name = first_value("nom", "")

    User = get_user_model()
    user, created = User.objects.get_or_create(username=username, defaults={"email": email})
    # Refresh attributes on every login to stay in sync with CAS directory.
    user.email = email or user.email
    user.first_name = first_name or user.first_name
    user.last_name = last_name or user.last_name
    if created:
        user.set_unusable_password()
    user.save()

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Authentifié via CAS Bordeaux INP.")
    return redirect(next_url)
