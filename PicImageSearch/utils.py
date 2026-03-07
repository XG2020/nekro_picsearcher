import re
from pathlib import Path
from typing import Any


def deep_get(dictionary: dict[str, Any], keys: str) -> Any | None:
    for key in keys.split("."):
        if list_search := re.search(r"(\S+)?\[(\d+)]", key):
            try:
                if list_search[1]:
                    dictionary = dictionary[list_search[1]]
                dictionary = dictionary[int(list_search[2])]
            except (KeyError, IndexError):
                return None
        else:
            try:
                dictionary = dictionary[key]
            except (KeyError, TypeError):
                return None
    return dictionary


def read_file(file: str | bytes | Path) -> bytes:
    if isinstance(file, bytes):
        return file
    if not Path(file).exists():
        raise FileNotFoundError(f"The file {file} does not exist.")
    with open(file, "rb") as f:
        return f.read()


def parse_html(html: str) -> Any:
    try:
        from nekro_agent.services.plugin.packages import dynamic_import_pkg
        dynamic_import_pkg("pyquery", "pyquery")
        dynamic_import_pkg("lxml", "lxml")
        dynamic_import_pkg("cssselect", "cssselect")
        from pyquery import PyQuery
        from lxml.html import fromstring
    except Exception as e:
        raise RuntimeError(
            f"Missing dependency 'pyquery/lxml': {e}. Ensure dynamic_import_pkg can fetch packages or install via pip."
        )
    return PyQuery(fromstring(html))
