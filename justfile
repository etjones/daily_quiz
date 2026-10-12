default:
    @just --list

run *args:
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
