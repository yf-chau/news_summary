import logging

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class TopicsList(BaseModel):
    topics: list[str]


class ArticleItem(BaseModel):
    headline: str
    uuid: str


class ArticlesListForATopic(BaseModel):
    topic: str
    articles: list[str]  # UUIDs only


class ArticlesByTopic(BaseModel):
    topics: list[ArticlesListForATopic]


class TopicSummary(BaseModel):
    topic: str
    summary: str


class TopicsSummary(BaseModel):
    topics: list[TopicSummary]


class SelectedArticles(BaseModel):
    selected: list[ArticleItem]


def is_valid_response(response: dict, model_class: type[BaseModel]) -> bool:
    try:
        model_class(**response)
        return True
    except ValidationError as e:
        logger.warning("Validation errors: %s", e)
        return False
