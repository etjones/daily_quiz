from jinja2 import Environment


def environment(**options: object) -> Environment:
    return Environment(**options)
