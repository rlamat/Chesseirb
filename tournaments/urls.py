from django.urls import path

from . import views

urlpatterns = [
    path("", views.tournament_list_open, name="tournament_list_open"),
    path("completed/", views.tournament_list_completed, name="tournament_list_completed"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("tournaments/create/", views.create_tournament, name="tournament_create"),
    path("tournaments/<int:pk>/edit/", views.edit_tournament, name="tournament_edit"),
    path("tournaments/<int:pk>/", views.tournament_detail, name="tournament_detail"),
    path("tournaments/<int:pk>/register/", views.register_to_tournament, name="tournament_register"),
    path("tournaments/<int:pk>/unregister/", views.unregister_from_tournament, name="tournament_unregister"),
    path("tournaments/<int:pk>/start/", views.start_tournament, name="tournament_start"),
    path("tournaments/<int:pk>/advance/", views.advance_round, name="tournament_next_round"),
    path("tournaments/<int:pk>/complete/", views.complete_tournament, name="tournament_complete"),
    path("tournaments/<int:pk>/open/", views.open_registration, name="tournament_open_reg"),
    path("tournaments/<int:pk>/close/", views.close_registration, name="tournament_close_reg"),
    path(
        "tournaments/<int:pk>/matches/<int:match_id>/result/",
        views.submit_result,
        name="submit_result",
    ),
    path("staff/users/", views.admin_users, name="admin_users"),
    path("admin/users/", views.admin_users, name="admin_users_legacy"),
]
