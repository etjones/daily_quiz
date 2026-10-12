from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path(
        "login", auth_views.LoginView.as_view(template_name="login.html"), name="login"
    ),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("", views.dashboard),
    path("students", views.students_view),
    path("students/select", views.select_student),
    path("students/default", views.set_default),
    path("mood", views.log_mood),
    path("day", views.build_day),
    path("day/<str:on>", views.day_page),
    path("files/<path:rel>", views.student_file),
    path("quiz", views.open_quiz),
    path("quiz/<int:quiz_id>", views.quiz_page),
    path("quiz/<int:quiz_id>/grade", views.grader),
    path("quiz/<int:quiz_id>/review", views.review_entry),
    path("quiz/<int:quiz_id>/photo", views.grade_photo),
    path("quiz/<int:quiz_id>/save", views.save_quiz),
    path("history", views.history),
    path("report", views.report_page),
    path("report/pdf", views.report_pdf),
    path("skills", views.skills_page),
    path("sentences", views.sentences_page),
    path("sentences/fill", views.fill_sentences),
    path("sentences/set", views.set_sentence),
    path("placement", views.placement_view),
]
