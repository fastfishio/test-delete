from pydantic import BaseModel


class PdpRequest(BaseModel):
    sku: str
