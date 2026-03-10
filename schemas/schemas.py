from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, validator

COURSE_CATEGORIES = {"Frontend Development", "Backend Development", "Systems Design"}
COURSE_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced", "Mastery"}
USER_ROLES = {"Admin", "Instructor", "Student"}
PUBLIC_REGISTRATION_ROLES = {"Student"}
QUESTION_DIFFICULTIES = {"Easy", "Medium", "Hard"}
QUESTION_TYPES = {"single", "multiple", "multiple_choice"}
LESSON_CONTENT_TYPES = {"lesson", "quiz", "test", "project", "resource"}
MEDIA_ASSET_TYPES = {"profile", "course"}


def _clean_text(value: str) -> str:
    return value.strip()


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    firstName: str
    lastName: str
    role: str = Field(default="Student")

    @validator("firstName", "lastName", pre=True)
    def validate_name(cls, value: str) -> str:
        value = _clean_text(value)
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return value

    @validator("password")
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must include both letters and numbers")
        return value

    @validator("role", pre=True, always=True)
    def validate_role(cls, value: Optional[str]) -> str:
        role = _clean_text(value or "Student").title()
        if role not in USER_ROLES:
            raise ValueError("Role must be Admin, Instructor, or Student")
        return role


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: EmailStr
    firstName: str
    lastName: str
    role: str
    isActive: bool
    avatarUrl: Optional[str] = None
    avatarPublicId: Optional[str] = None

    @validator("firstName", "lastName", pre=True)
    def validate_name(cls, value: str) -> str:
        value = _clean_text(value)
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return value

    @validator("role")
    def validate_role(cls, value: str) -> str:
        role = _clean_text(value).title()
        if role not in USER_ROLES:
            raise ValueError("Role must be Admin, Instructor, or Student")
        return role


class UserPatch(BaseModel):
    email: Optional[EmailStr] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    role: Optional[str] = None
    isActive: Optional[bool] = None
    avatarUrl: Optional[str] = None
    avatarPublicId: Optional[str] = None

    @validator("firstName", "lastName", pre=True)
    def validate_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = _clean_text(value)
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters long")
        return value

    @validator("role")
    def validate_optional_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        role = _clean_text(value).title()
        if role not in USER_ROLES:
            raise ValueError("Role must be Admin, Instructor, or Student")
        return role


class UserStatusUpdate(BaseModel):
    isActive: bool


class PasswordChangeRequest(BaseModel):
    currentPassword: str
    newPassword: str = Field(min_length=8, max_length=128)

    @validator("newPassword")
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must include both letters and numbers")
        return value


class CourseEnroll(BaseModel):
    courseSlug: str
    category: str = Field(default="Frontend Development")
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
    points: int = Field(default=1, ge=1, le=10)
    questionType: str = Field(default="multiple_choice")
    difficulty: str = Field(default="Medium")
    isActive: bool = True
    timeLimit: int = Field(default=60, ge=10, le=600)

    @validator("quizId", "question", "correctAnswer", pre=True)
    def validate_required_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("options")
    def validate_options(cls, value: List[str]) -> List[str]:
        cleaned = [_clean_text(option) for option in value if _clean_text(option)]
        if len(cleaned) < 2:
            raise ValueError("At least 2 options are required")
        return cleaned

    @validator("correctAnswer")
    def validate_correct_answer(cls, value: str, values) -> str:
        if "options" in values and value not in values["options"]:
            raise ValueError("Correct answer must be one of the options")
        return value

    @validator("questionType")
    def validate_question_type(cls, value: str) -> str:
        value = _clean_text(value).lower()
        if value not in QUESTION_TYPES:
            raise ValueError("Question type must be single, multiple, or multiple_choice")
        return value

    @validator("difficulty")
    def validate_difficulty(cls, value: str) -> str:
        value = _clean_text(value).title()
        if value not in QUESTION_DIFFICULTIES:
            raise ValueError("Difficulty must be Easy, Medium, or Hard")
        return value


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
    thumbnailPublicId: Optional[str] = ""

    @validator("slug", "title", "description", pre=True)
    def validate_course_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("category")
    def validate_category(cls, value: str) -> str:
        value = _clean_text(value)
        if value not in COURSE_CATEGORIES:
            raise ValueError("Category must be Frontend Development, Backend Development, or Systems Design")
        return value

    @validator("difficulty")
    def validate_course_difficulty(cls, value: str) -> str:
        value = _clean_text(value).title()
        if value not in COURSE_DIFFICULTIES:
            raise ValueError("Difficulty must be Beginner, Intermediate, Advanced, or Mastery")
        return value


class CourseProgressUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)
    completed: Optional[bool] = False


class LessonInput(BaseModel):
    title: str
    slug: str
    summary: str
    durationMinutes: int = Field(default=15, ge=1)
    contentType: str = Field(default="lesson")
    quizId: Optional[str] = None
    quizTitle: Optional[str] = None

    @validator("title", "slug", "summary", pre=True)
    def validate_lesson_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("contentType")
    def validate_content_type(cls, value: str) -> str:
        value = _clean_text(value).lower()
        if value not in LESSON_CONTENT_TYPES:
            raise ValueError("Content type must be lesson, quiz, test, project, or resource")
        return value


class ModuleInput(BaseModel):
    title: str
    description: str
    order: int = Field(ge=1)
    lessons: List[LessonInput] = []
    assessmentTitle: Optional[str] = None
    assessmentQuizId: Optional[str] = None

    @validator("title", "description", pre=True)
    def validate_module_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class MilestoneProjectInput(BaseModel):
    title: str
    description: str
    milestoneOrder: int = Field(ge=1)
    estimatedHours: int = Field(default=4, ge=1)
    deliverables: List[str] = []
    completionThreshold: int = Field(default=70, ge=50, le=100)

    @validator("title", "description", pre=True)
    def validate_project_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("deliverables", each_item=True)
    def validate_deliverable(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Deliverables cannot be empty")
        return value


class CourseCurriculumUpsert(BaseModel):
    overview: str = ""
    modules: List[ModuleInput] = []
    milestoneProjects: List[MilestoneProjectInput] = []


class MediaUploadSignatureRequest(BaseModel):
    assetType: str
    publicId: Optional[str] = None

    @validator("assetType")
    def validate_asset_type(cls, value: str) -> str:
        asset_type = _clean_text(value).lower()
        if asset_type not in MEDIA_ASSET_TYPES:
            raise ValueError("Asset type must be profile or course")
        return asset_type

    @validator("publicId", pre=True)
    def validate_public_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None
