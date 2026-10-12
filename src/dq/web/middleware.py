"""Opens dq's own database for each request and turns domain errors into friendly pages."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from ..db import DB
from .theme import house_context


class PageError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def error_page(request: HttpRequest, message: str, status: int) -> HttpResponse:
    ctx = {
        **house_context(request),
        "title": "Problem",
        "message": message,
        "students": [],
    }
    return render(request, "error.html", ctx, status=status)


class DqMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.db = DB(settings.DQ_HOME / "dq.db")
        try:
            return self.get_response(request)
        finally:
            request.db.close()

    def process_exception(
        self, request: HttpRequest, exc: Exception
    ) -> HttpResponse | None:
        if isinstance(exc, PageError):
            return error_page(request, exc.message, exc.status)
        return None
