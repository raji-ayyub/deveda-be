from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, validator

COURSE_CATEGORIES = {"Frontend Development", "Backend Development", "Systems Design"}
COURSE_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced", "Mastery"}
USER_ROLES = {"Admin", "Instructor", "Student"}
PUBLIC_REGISTRATION_ROLES = {"Student", "Instructor"}
QUESTION_DIFFICULTIES = {"Easy", "Medium", "Hard"}
QUESTION_TYPES = {"single", "multiple", "multiple_choice"}
LESSON_CONTENT_TYPES = {"lesson", "quiz", "test", "project", "resource"}
LESSON_GAME_KEYS = {
    "semantic-sleuth",
    "grid-studio",
    "ui-mood-runway",
    "data-remix-club",
    "signal-rescue-mission",
}
PLAYGROUND_MODES = {"web", "javascript"}
PLAYGROUND_CHECK_TYPES = {"includes", "output"}
PLAYGROUND_TARGETS = {"html", "css", "js", "console"}
MEDIA_ASSET_TYPES = {"profile", "course"}
AGENT_TYPES = {"course_builder", "progress_analyst", "lesson_tutor", "platform_support"}
CONTENT_INGESTION_TYPES = {"course", "lesson", "quiz", "question_bank"}
CONTENT_GENERATION_ACTION_TYPES = {
    "create_course_shell",
    "generate_overview",
    "generate_module",
    "generate_questions",
}
AGENT_REQUEST_STATUSES = {"pending", "approved", "rejected"}
AGENT_ACTION_TYPES = {
    "draft_course_catalog",
    "create_course_shell",
    "create_curriculum_draft",
    "apply_curriculum_to_course",
    "save_planning_note",
    "suggest_lesson_content",
    "plan_lesson_content",
    "generate_lesson_content",
    "plan_course_content",
    "generate_course_content",
    "generate_module_content",
    "generate_question_content",
}


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


class PrivateAdminCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    firstName: str
    lastName: str
    adminSetupSecret: str = Field(min_length=1)

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

    @validator("adminSetupSecret", pre=True)
    def validate_admin_secret(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Admin setup secret is required")
        return value


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
    completedLessonSlugs: Optional[List[str]] = None
    currentLessonSlug: Optional[str] = None

    @validator("completedLessonSlugs", each_item=True)
    def validate_completed_lesson_slug(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Completed lesson slugs cannot be empty")
        return value

    @validator("currentLessonSlug", pre=True)
    def clean_current_lesson_slug(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class LessonGameProgressUpdate(BaseModel):
    gameKey: str
    totalRounds: int = Field(default=1, ge=1)
    score: int = Field(default=0, ge=0)
    completedRounds: int = Field(default=0, ge=0)
    accuracy: int = Field(default=0, ge=0, le=100)
    completed: bool = Field(default=False)

    @validator("gameKey", pre=True)
    def validate_game_key(cls, value: str) -> str:
        value = _clean_text(value)
        if value not in LESSON_GAME_KEYS:
            raise ValueError("Lesson game key is not recognized")
        return value

    @validator("completedRounds")
    def validate_completed_rounds(cls, value: int, values) -> int:
        total_rounds = int(values.get("totalRounds") or 0)
        if total_rounds and value > total_rounds:
            raise ValueError("Completed rounds cannot exceed total rounds")
        return value

    @validator("score")
    def validate_score(cls, value: int, values) -> int:
        total_rounds = int(values.get("totalRounds") or 0)
        if total_rounds and value > total_rounds:
            raise ValueError("Score cannot exceed total rounds")
        return value


class LessonPlaygroundCheckInput(BaseModel):
    label: str
    type: str = Field(default="includes")
    target: str = Field(default="js")
    value: str

    @validator("label", "value", pre=True)
    def validate_check_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("type")
    def validate_check_type(cls, value: str) -> str:
        value = _clean_text(value).lower()
        if value not in PLAYGROUND_CHECK_TYPES:
            raise ValueError("Check type must be includes or output")
        return value

    @validator("target")
    def validate_check_target(cls, value: str) -> str:
        value = _clean_text(value).lower()
        if value not in PLAYGROUND_TARGETS:
            raise ValueError("Check target must be html, css, js, or console")
        return value


class LessonPlaygroundInput(BaseModel):
    mode: str = Field(default="web")
    instructions: str = ""
    starterHtml: Optional[str] = ""
    starterCss: Optional[str] = ""
    starterJs: Optional[str] = ""
    checks: List[LessonPlaygroundCheckInput] = []

    @validator("mode")
    def validate_playground_mode(cls, value: str) -> str:
        value = _clean_text(value).lower()
        if value not in PLAYGROUND_MODES:
            raise ValueError("Playground mode must be web or javascript")
        return value

    @validator("instructions", "starterHtml", "starterCss", "starterJs", pre=True)
    def clean_playground_text(cls, value: Optional[str]) -> str:
        return _clean_text(value or "")


class LessonInput(BaseModel):
    title: str
    slug: str
    libraryLessonSlug: Optional[str] = None
    source: Optional[str] = "manual"
    generationStatus: Optional[str] = "generated"
    summary: str
    durationMinutes: int = Field(default=15, ge=1)
    contentType: str = Field(default="lesson")
    quizId: Optional[str] = None
    quizTitle: Optional[str] = None
    learningObjectives: List[str] = []
    keyTakeaways: List[str] = []
    learningFlow: List[str] = []
    contentMarkdown: str = ""
    visualAidMarkdown: Optional[str] = ""
    practicePrompt: Optional[str] = ""
    instructorNotes: Optional[str] = ""
    gameKey: Optional[str] = None
    playground: Optional[LessonPlaygroundInput] = None

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

    @validator(
        "libraryLessonSlug",
        "source",
        "generationStatus",
        "quizId",
        "quizTitle",
        "contentMarkdown",
        "visualAidMarkdown",
        "practicePrompt",
        "instructorNotes",
        "gameKey",
        pre=True,
    )
    def clean_optional_lesson_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _clean_text(value)

    @validator("gameKey")
    def validate_game_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in LESSON_GAME_KEYS:
            raise ValueError("Lesson game key is not recognized")
        return value

    @validator("generationStatus")
    def validate_generation_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        status = _clean_text(value).lower()
        if status not in {"planned", "generated"}:
            raise ValueError("Generation status must be planned or generated")
        return status

    @validator("learningObjectives", "keyTakeaways", "learningFlow", each_item=True)
    def validate_learning_list(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("List items cannot be empty")
        return value


class ModuleInput(BaseModel):
    title: str
    description: str
    order: int = Field(ge=1)
    source: Optional[str] = "manual"
    generationStatus: Optional[str] = "generated"
    lessons: List[LessonInput] = []
    assessmentTitle: Optional[str] = None
    assessmentQuizId: Optional[str] = None

    @validator("title", "description", pre=True)
    def validate_module_text(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @validator("source", "generationStatus", "assessmentTitle", "assessmentQuizId", pre=True)
    def clean_optional_module_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None

    @validator("generationStatus")
    def validate_module_generation_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        status = _clean_text(value).lower()
        if status not in {"planned", "generated"}:
            raise ValueError("Generation status must be planned or generated")
        return status


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
    learningFlow: List[str] = []
    visualAidMarkdown: Optional[str] = ""
    modules: List[ModuleInput] = []
    milestoneProjects: List[MilestoneProjectInput] = []

    @validator("overview", "visualAidMarkdown", pre=True)
    def clean_curriculum_text(cls, value: Optional[str]) -> str:
        return _clean_text(value or "")

    @validator("learningFlow", each_item=True)
    def validate_curriculum_learning_flow(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Learning flow steps cannot be empty")
        return value


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


class AgentRequestCreate(BaseModel):
    agentType: str
    displayName: Optional[str] = None
    notes: Optional[str] = ""
    courseSlug: Optional[str] = None
    lessonSlug: Optional[str] = None
    targetUserId: Optional[str] = None

    @validator("agentType")
    def validate_agent_type(cls, value: str) -> str:
        agent_type = _clean_text(value).lower()
        if agent_type not in AGENT_TYPES:
            raise ValueError("Unknown agent type")
        return agent_type

    @validator("displayName", "notes", "courseSlug", "lessonSlug", "targetUserId", pre=True)
    def clean_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class AgentApprovalUpdate(BaseModel):
    status: str
    adminNotes: Optional[str] = ""

    @validator("status")
    def validate_status(cls, value: str) -> str:
        status_value = _clean_text(value).lower()
        if status_value not in AGENT_REQUEST_STATUSES:
            raise ValueError("Status must be pending, approved, or rejected")
        return status_value

    @validator("adminNotes", pre=True)
    def clean_admin_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _clean_text(value)


class AgentThreadCreate(BaseModel):
    assignmentId: str
    title: Optional[str] = None
    initialMessage: Optional[str] = None
    courseSlug: Optional[str] = None
    lessonSlug: Optional[str] = None

    @validator("assignmentId", pre=True)
    def validate_assignment_id(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Assignment is required")
        return value

    @validator("title", "initialMessage", "courseSlug", "lessonSlug", pre=True)
    def clean_thread_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class AgentMessageCreate(BaseModel):
    message: str
    courseSlug: Optional[str] = None
    courseTitle: Optional[str] = None
    lessonSlug: Optional[str] = None
    lessonTitle: Optional[str] = None
    currentProgress: Optional[int] = Field(default=None, ge=0, le=100)

    @validator("message", pre=True)
    def validate_message(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Message is required")
        return value

    @validator("courseSlug", "courseTitle", "lessonSlug", "lessonTitle", pre=True)
    def clean_message_context(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class AgentActionCreate(BaseModel):
    actionType: str
    artifactId: Optional[str] = None
    courseSlug: Optional[str] = None
    lessonSlug: Optional[str] = None
    moduleOrder: Optional[int] = Field(default=None, ge=1)
    questionCount: Optional[int] = Field(default=None, ge=1, le=10)
    targetUserId: Optional[str] = None
    instruction: Optional[str] = ""
    draftPayload: Optional[dict] = None

    @validator("actionType")
    def validate_action_type(cls, value: str) -> str:
        action_type = _clean_text(value).lower()
        if action_type not in AGENT_ACTION_TYPES:
            raise ValueError("Unknown action type")
        return action_type

    @validator("artifactId", "courseSlug", "lessonSlug", "targetUserId", "instruction", pre=True)
    def clean_action_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = _clean_text(value)
        return cleaned or None


class ContentGenerationActionRequest(BaseModel):
    actionType: str
    moduleOrder: Optional[int] = Field(default=None, ge=1)
    questionCount: Optional[int] = Field(default=None, ge=1, le=20)
    instructions: Optional[str] = ""

    @validator("actionType")
    def validate_generation_action_type(cls, value: str) -> str:
        action_type = _clean_text(value).lower()
        if action_type not in CONTENT_GENERATION_ACTION_TYPES:
            raise ValueError("Unknown content generation action type")
        return action_type

    @validator("instructions", pre=True)
    def clean_generation_instruction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _clean_text(value)
