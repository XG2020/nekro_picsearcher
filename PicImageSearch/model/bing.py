from collections.abc import Callable
from typing import Any

from typing_extensions import override

from .base import BaseSearchItem, BaseSearchResponse


class BingItem(BaseSearchItem):
    def __init__(self, data: dict[str, Any], **kwargs: Any):
        super().__init__(data, **kwargs)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.title: str = data.get("name", "")
        self.url: str = data.get("hostPageUrl", "")
        self.thumbnail: str = data.get("thumbnailUrl", "")
        self.image_url: str = data.get("contentUrl", "")


class RelatedSearchItem:
    def __init__(self, data: dict[str, Any]):
        self.text: str = data.get("text", "")
        self.thumbnail: str = data.get("thumbnail", {}).get("url", "")


class PagesIncludingItem:
    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", "")
        self.thumbnail: str = data.get("thumbnailUrl", "")
        self.url: str = data.get("hostPageUrl", "")
        self.image_url: str = data.get("contentUrl", "")


class VisualSearchItem:
    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", "")
        self.thumbnail: str = data.get("thumbnailUrl", "")
        self.url: str = data.get("hostPageUrl", "")
        self.image_url: str = data.get("contentUrl", "")


class Attraction:
    def __init__(self, data: dict[str, Any]):
        self.url: str = data.get("attractionUrl", "")
        self.title: str = data.get("title", "")
        self.search_url: str = data.get("requeryUrl", "")
        self.interest_types: list[str] = data.get("interestTypes", [])


class TravelCard:
    def __init__(self, data: dict[str, Any]):
        self.card_type: str = data.get("cardType", "")
        self.title: str = data.get("title", "")
        self.url: str = data.get("clickUrl", "")
        self.image_url: str = data.get("image", "")
        self.image_source_url: str = data.get("imageSourceUrl", "")


class TravelInfo:
    def __init__(self, data: dict[str, Any]):
        self.destination_name: str = data.get("destinationName", "")
        self.travel_guide_url: str = data.get("travelGuideUrl", "")
        self.attractions: list[Attraction] = [Attraction(x) for x in data.get("attractions", [])]
        self.travel_cards: list[TravelCard] = [TravelCard(x) for x in data.get("travelCards", [])]


class EntityItem:
    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", "")
        self.thumbnail: str = data.get("image", {}).get("thumbnailUrl", "")
        self.description: str = data.get("description", "")
        self.profiles: list[dict[str, str]] = []
        if social_media := data.get("socialMediaInfo"):
            self.profiles = [
                {
                    "url": profile.get("profileUrl"),
                    "social_network": profile.get("socialNetwork"),
                }
                for profile in social_media.get("profiles", [])
            ]
        self.short_description: str = data.get("entityPresentationInfo", {}).get("entityTypeDisplayHint", "")


class BingResponse(BaseSearchResponse[BingItem]):
    def __init__(self, resp_data: dict[str, Any], resp_url: str, **kwargs: Any):
        super().__init__(resp_data, resp_url, **kwargs)

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        self.pages_including: list[PagesIncludingItem] = []
        self.visual_search: list[VisualSearchItem] = []
        self.related_searches: list[RelatedSearchItem] = []
        self.best_guess: str | None = None
        self.travel: TravelInfo | None = None
        self.entities: list[EntityItem] = []
        if tags := resp_data.get("tags"):
            for tag in tags:
                for action in tag.get("actions", []):
                    self._parse_action(action)

    def _parse_action(self, action: dict[str, Any]) -> None:
        action_type: str = action.get("actionType", "")
        action_handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            "PagesIncluding": self._handle_pages_including,
            "VisualSearch": self._handle_visual_search,
            "RelatedSearches": self._handle_related_searches,
            "BestRepresentativeQuery": self._handle_best_query,
            "Travel": self._handle_travel,
            "Entity": self._handle_entity,
        }
        if handler := action_handlers.get(action_type):
            handler(action)

    def _handle_pages_including(self, action: dict[str, Any]) -> None:
        if value := action.get("data", {}).get("value"):
            self.pages_including.extend([PagesIncludingItem(val) for val in value])

    def _handle_visual_search(self, action: dict[str, Any]) -> None:
        if value := action.get("data", {}).get("value"):
            self.visual_search.extend([VisualSearchItem(val) for val in value])

    def _handle_related_searches(self, action: dict[str, Any]) -> None:
        if value := action.get("data", {}).get("value"):
            self.related_searches.extend([RelatedSearchItem(val) for val in value])

    def _handle_best_query(self, action: dict[str, Any]) -> None:
        self.best_guess = action.get("displayName")

    def _handle_travel(self, action: dict[str, Any]) -> None:
        self.travel = TravelInfo(action.get("data", {}))

    def _handle_entity(self, action: dict[str, Any]) -> None:
        if data := action.get("data"):
            self.entities.append(EntityItem(data))
