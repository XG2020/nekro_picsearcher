from typing import Any, NamedTuple

from typing_extensions import override

from .base import BaseSearchItem, BaseSearchResponse


class Character(NamedTuple):
    name: str
    work: str


class AnimeTraceItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.box: list[float] = data["box"]
        self.box_id: str = data["box_id"]
        character_data = data["character"]
        self.characters: list[Character] = []
        for char_info in character_data:
            character = Character(char_info["character"], char_info["work"])
            self.characters.append(character)


class AnimeTraceResponse(BaseSearchResponse[AnimeTraceItem]):
    def __init__(self, resp_data: dict[str, Any], resp_url: str, **kwargs: Any) -> None:
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        self.code: int = resp_data["code"]
        self.ai: bool = resp_data.get("ai", False)
        self.trace_id: str = resp_data["trace_id"]
        results = resp_data["data"]
        self.raw: list[AnimeTraceItem] = [AnimeTraceItem(item) for item in results]
