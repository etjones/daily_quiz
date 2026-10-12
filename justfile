default:
    @just --list

port := env("DQ_PORT", "8000")

run:
    DQ_DEBUG=1 uv run python manage.py migrate --verbosity 0
    DQ_DEBUG=1 uv run python manage.py runserver 127.0.0.1:{{port}}

adduser name:
    uv run python manage.py createsuperuser --username {{name}} --email ''

passwd name:
    uv run python manage.py changepassword {{name}}

dq *args:
    uv run dq {{args}}

test *args:
    uv run pytest -q {{args}}

watch:
    uv run --with pytest-watcher ptw . --now

validate:
    uv run dq validate

status name="":
    uv run dq status {{name}}

skills *args:
    uv run dq skills {{args}}

student *args:
    uv run dq default {{args}}

init name:
    uv run dq init {{name}}

placement name="":
    uv run dq placement {{name}}

oral name="":
    uv run dq oral {{name}}

grade *args:
    uv run dq grade {{args}}

mood *args:
    uv run dq mood {{args}}

next name="":
    uv run dq next {{name}}

report name="":
    uv run dq report {{name}} --pdf

lint:
    uvx ruff check .

with-secrets +args:
    set -a; . ~/.config/op/token.env; set +a; op run --env-file=.env -- just {{args}}
