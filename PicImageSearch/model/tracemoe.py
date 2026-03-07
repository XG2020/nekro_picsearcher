from typing import Any

from typing_extensions import override

from .base import BaseSearchItem, BaseSearchResponse


class TraceMoeMe:
    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.priority: int = data["priority"]
        self.concurrency: int = data["concurrency"]
        self.quota: int = data["quota"]
        self.quotaUsed: int = data["quotaUsed"]


class TraceMoeItem(BaseSearchItem):
    def __init__(
        self,
        data: dict[str, Any],
        mute: bool = False,
        size: str | None = None,
    ):
        super().__init__(data, mute=mute, size=size)

    @override
    def _parse_data(self, data: dict[str, Any], **kwargs: Any) -> None:
        self.anime_info: dict[str, Any] = {}
        self.idMal: int = 0
        self.title_native: str = ""
        self.title_english: str = ""
        self.title_romaji: str = ""
        self.title_chinese: str = ""
        self.anilist_id: int = 0
        self.synonyms: list[str] = []
        self.isAdult: bool = False
        self.type: str = ""
        self.format: str = ""
        self.start_date: dict[str, Any] = {}
        self.end_date: dict[str, Any] = {}
        self.cover_image: str = ""

        if anilist_data := data.get("anilist"):
            self.anilist_id = anilist_data.get("id", 0)
            self.anime_info = anilist_data
            self.idMal = anilist_data.get("idMal", 0)
            title = anilist_data.get("title", {})
            self.title_native = title.get("native", "")
            self.title_romaji = title.get("romaji", "")
            self.title_english = title.get("english", "")
            self.title_chinese = title.get("chinese", "")
            self.synonyms = anilist_data.get("synonyms", [])
            self.isAdult = anilist_data.get("isAdult", False)
            self.type = anilist_data.get("type", "")
            self.format = anilist_data.get("format", "")
            self.start_date = anilist_data.get("startDate", {})
            self.end_date = anilist_data.get("endDate", {})
            cover = anilist_data.get("coverImage", {})
            self.cover_image = cover.get("large", "") if isinstance(cover, dict) else ""

        self.filename: str = data["filename"]
        self.episode: int = data["episode"]
        self.From: float = data["from"]
        self.To: float = data["to"]
        self.similarity: float = float(f"{data['similarity'] * 100:.2f}")
        self.video: str = data["video"]
        self.image: str = data["image"]
        size = kwargs.get("size")
        if size in ["l", "s", "m"]:
            self.video += f"&size={size}"
            self.image += f"&size={size}"
        if kwargs.get("mute"):
            self.video += "&mute"


class TraceMoeResponse(BaseSearchResponse[TraceMoeItem]):
    def __init__(
        self,
        resp_data: dict[str, Any],
        resp_url: str,
        mute: bool,
        size: str | None,
    ):
        super().__init__(resp_data, resp_url, mute=mute, size=size)

    @override
    def _parse_response(self, resp_data: dict[str, Any], **kwargs: Any) -> None:
        res_docs = resp_data["result"]
        self.raw.extend(
            [
                TraceMoeItem(
                    i,
                    mute=kwargs.get("mute", False),
                    size=kwargs.get("size"),
                )
                for i in res_docs
            ]
        )
        self.frameCount: int = resp_data["frameCount"]
        self.error: str = resp_data["error"]
