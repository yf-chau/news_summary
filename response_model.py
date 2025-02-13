from pydantic import BaseModel, RootModel, ValidationError
from typing import List, Dict


# Topics list model
class TopicsList(BaseModel):
    """
    Model for generated topics
    """

    topics: List[str]


class ArticleItem(BaseModel):
    """
    Model for a single article item
    """

    headline: str
    uuid: str


class ArticlesListForATopic(BaseModel):
    """
    Model for a list of article items for a single topic
    """

    topic: str
    articles: List[ArticleItem]


class ArticlesByTopic(BaseModel):
    """
    Model for articles grouped by topics

    """

    topics: List[ArticlesListForATopic]


class TopicSummary(BaseModel):
    """
    Model for a single topic summary
    """

    topic: str
    summary: str


class TopicsSummary(BaseModel):
    """
    Model for a list of topic summaries
    """

    topics: List[TopicSummary]


class Score(BaseModel):
    """
    Model for generated score
    """

    summary_id: int
    score: int
    reason: str


class ScoreModel(BaseModel):
    """
    Model for generated scores
    """

    scores: List[Score]


# Utility function for validation
def is_valid_response(response: dict, model_class: type[BaseModel]) -> bool:
    """
    Validate response using Pydantic model

    Args:
        response: JSON response to validate
        model_class: Pydantic model class to validate against

    Returns:
        bool: Whether the response is valid
    """
    try:
        # Attempt to parse and validate the response
        model_class(**response)
        return True
    except ValidationError as e:
        # Optionally log the validation errors
        print(f"Validation errors: {e}")
        return False
