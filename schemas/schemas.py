# app/schemas/schemas.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    firstName: str
    lastName: str
    role: str = Field(default="User")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    email: EmailStr
    firstName: str
    lastName: str
    role: str
    isActive: bool

class UserPatch(BaseModel):
    email: Optional[EmailStr] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    role: Optional[str] = None
    isActive: Optional[bool] = None

class CourseEnroll(BaseModel):
    courseSlug: str
    category: str = Field(default="General")
    difficulty: str = Field(default="Beginner")

class QuizAttemptCreate(BaseModel):
    quizId: str
    score: int = Field(ge=0, le=100)
    courseSlug: Optional[str] = None

class QuestionCreate(BaseModel):
    quizId: str
    question: str
    options: List[str]
    correctAnswer: str
    explanation: Optional[str] = ""
    points: int = Field(default=1, ge=1)
    questionType: str = Field(default="multiple_choice")

    @validator('options')
    def validate_options(cls, v):
        if len(v) < 2:
            raise ValueError('At least 2 options are required')
        return v
    
    @validator('correctAnswer')
    def validate_correct_answer(cls, v, values):
        if 'options' in values and v not in values['options']:
            raise ValueError('Correct answer must be one of the options')
        return v

class CourseCatalogCreate(BaseModel):
    slug: str
    title: str
    description: str
    category: str
    difficulty: str = Field(default="Beginner")
    duration: Optional[int] = 0
    totalQuizzes: Optional[int] = 0
    totalLessons: Optional[int] = 0
    instructor: Optional[str] = ""
    prerequisites: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    thumbnail: Optional[str] = ""

class CourseProgressUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)
    completed: Optional[bool] = False