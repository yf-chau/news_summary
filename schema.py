from pydantic import BaseModel
from response_model import TopicsSummary


# Generate JSON Schema
schema = TopicsSummary.model_json_schema()

print(schema)
