from pydantic import BaseModel
from typing import List, Optional

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    recipes: List["Recipe"] = []

    class Config:
        orm_mode = True

class RecipeBase(BaseModel):
    title: str
    description: Optional[str] = None
    ingredients: str
    instructions: str

class RecipeCreate(RecipeBase):
    pass

class Recipe(RecipeBase):
    id: int
    owner_id: int

    class Config:
        orm_mode = True
