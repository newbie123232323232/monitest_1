from pydantic import BaseModel


class ProbeRegionItemResponse(BaseModel):
    code: str
    name: str
