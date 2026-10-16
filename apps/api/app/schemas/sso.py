from pydantic import BaseModel


class SSOLoginResponse(BaseModel):
    authorization_url: str


class SSOCallbackRequest(BaseModel):
    code: str
    state: str
