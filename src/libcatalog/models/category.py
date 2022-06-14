from typing import List
from pydantic import BaseModel


class Category(BaseModel):
    id_category: int
    id_category_parent: int | None
    code: str
    en_name: str
    ar_name: str
    children: List[int] = []

    def name(self, lang: str = 'en') -> str:
        if lang == 'ar':
            return self.ar_name
        else:
            return self.en_name
