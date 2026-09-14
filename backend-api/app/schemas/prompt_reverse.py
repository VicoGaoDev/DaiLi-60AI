from pydantic import BaseModel


class PromptReverseRequest(BaseModel):
    image_url: str


class PromptReverseResponse(BaseModel):
    prompt: str
