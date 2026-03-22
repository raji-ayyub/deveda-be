from typing import Optional

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from database.database import ensure_indexes
from schemas.schemas import (
    AgentActionCreate,
    AgentApprovalUpdate,
    AgentMessageCreate,
    AgentRequestCreate,
    AgentThreadCreate,
    CourseCatalogCreate,
    CourseCurriculumUpsert,
    CourseEnroll,
    CourseProgressUpdate,
    ContentGenerationActionRequest,
    MediaUploadSignatureRequest,
    PasswordChangeRequest,
    PrivateAdminCreateRequest,
    QuestionCreate,
    QuizAttemptCreate,
    UserCreate,
    UserLogin,
    UserPatch,
    UserStatusUpdate,
    UserUpdate,
)
from services import achievement_services, admin_services, agent_services, auth_services, content_intake_services, content_services, course_seed_services, course_services, lesson_library_services, media_services, quiz_services

openapi_tags = [
    {
        "name": "System",
        "description": "Health and service-level endpoints for confirming the API is reachable.",
    },
    {
        "name": "Authentication",
        "description": "Registration, login, session inspection, and password management endpoints.",
    },
    {
        "name": "Users",
        "description": "User account administration, profile updates, status changes, and deletion.",
    },
    {
        "name": "Course Enrollment",
        "description": "Enrollment and learner progress endpoints scoped to individual users.",
    },
    {
        "name": "Course Catalog",
        "description": "Course catalog CRUD, discovery, and enrollment overview endpoints.",
    },
    {
        "name": "Curriculum",
        "description": "Curriculum structure endpoints for lessons, modules, and milestone projects.",
    },
    {
        "name": "Lesson Library",
        "description": "Reusable lesson records that surface course-linked sub-lessons and access status.",
    },
    {
        "name": "Content Intake",
        "description": "Upload-first content ingestion endpoints for agent-assisted course, lesson, and quiz generation.",
    },
    {
        "name": "Quizzes",
        "description": "Quiz listing, question retrieval by quiz, and learner attempt submission.",
    },
    {
        "name": "Question Bank",
        "description": "Question authoring and maintenance endpoints for admins and instructors.",
    },
    {
        "name": "Analytics",
        "description": "Dashboard summary, activity, and chart endpoints for administrative views.",
    },
    {
        "name": "Media",
        "description": "Signed upload helpers for learner avatars and course imagery.",
    },
    {
        "name": "Achievements",
        "description": "Milestones, certificates, and shareable learner accomplishments.",
    },
    {
        "name": "Agents",
        "description": "Multi-agent orchestration, approvals, chat threads, and role-aware learning support.",
    },
]

app = FastAPI(
    title="Deveda Coding Platform API",
    description="Backend API for authentication, learner management, course delivery, quizzes, and admin analytics.",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def initialize_database_state():
    await ensure_indexes()
    await course_seed_services.ensure_frontend_blank_file_milestone_seed()


@app.get(
    "/",
    tags=["System"],
    summary="Health check",
    description="Returns a simple confirmation that the Deveda backend is running.",
)
def root():
    return {"message": "Learning Platform API up and running"}


@app.post(
    "/register",
    status_code=201,
    tags=["Authentication"],
    summary="Register a student or instructor account",
    description="Creates a new public student or instructor account and returns the authenticated session payload.",
)
async def register_user(payload: UserCreate):
    return await auth_services.AuthService.register_user(payload)


@app.post(
    "/auth/private-admin/register",
    status_code=201,
    tags=["Authentication"],
    summary="Create a private admin account",
    description="Creates an admin account when the correct private setup secret is supplied.",
)
async def register_private_admin(payload: PrivateAdminCreateRequest):
    return await auth_services.AuthService.register_private_admin(payload)


@app.post(
    "/login",
    tags=["Authentication"],
    summary="Log in a user",
    description="Authenticates a user with email and password and returns a fresh access token.",
)
async def login_user(payload: UserLogin):
    return await auth_services.AuthService.login_user(payload)


@app.get(
    "/auth/me",
    tags=["Authentication"],
    summary="Get current session",
    description="Returns the currently authenticated user linked to the supplied bearer token.",
)
async def get_current_session(current_user: dict = Depends(auth_services.get_current_user)):
    return await auth_services.AuthService.get_session(current_user)


@app.post(
    "/auth/change-password",
    tags=["Authentication"],
    summary="Change current password",
    description="Validates the current password and replaces it with a new password for the logged-in user.",
)
async def change_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await auth_services.AuthService.change_password(current_user, payload)


@app.post(
    "/media/uploads/signature",
    tags=["Media"],
    summary="Create Cloudinary upload signature",
    description="Generates a signed Cloudinary payload for direct browser uploads of profile avatars and course thumbnails.",
)
async def create_upload_signature(
    payload: MediaUploadSignatureRequest,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await media_services.MediaService.create_upload_signature(current_user, payload)


@app.get(
    "/users",
    tags=["Users"],
    summary="List users",
    description="Returns all users with high-level enrollment and quiz activity counts.",
)
async def get_all_users(current_user: dict = Depends(auth_services.require_roles("Admin"))):
    return await auth_services.UserService.get_all_users()


@app.post(
    "/users",
    status_code=201,
    tags=["Users"],
    summary="Create a user",
    description="Creates a user account as an admin action and initializes the profile and account records.",
)
async def create_user(
    payload: UserCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin")),
):
    return await auth_services.UserService.create_user(payload)


@app.get(
    "/users/{user_id}",
    tags=["Users"],
    summary="Get a user",
    description="Returns a single user's account details, profile, and learner statistics.",
)
async def get_user(user_id: str, current_user: dict = Depends(auth_services.get_current_user)):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await auth_services.UserService.get_user(user_id)


@app.put(
    "/users/{user_id}",
    tags=["Users"],
    summary="Replace a user",
    description="Fully updates a user's editable account fields and role or status where allowed.",
)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await auth_services.UserService.update_user(user_id, payload, current_user)


@app.patch(
    "/users/{user_id}",
    tags=["Users"],
    summary="Patch a user",
    description="Partially updates selected user fields without sending the full user payload.",
)
async def patch_user(
    user_id: str,
    payload: UserPatch,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await auth_services.UserService.patch_user(user_id, payload, current_user)


@app.patch(
    "/users/{user_id}/status",
    tags=["Users"],
    summary="Update user status",
    description="Toggles whether a user account is active or inactive.",
)
async def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    current_user: dict = Depends(auth_services.require_roles("Admin")),
):
    return await auth_services.UserService.update_user_status(user_id, payload)


@app.delete(
    "/users/{user_id}",
    tags=["Users"],
    summary="Delete a user",
    description="Deletes a user account and removes related profile, course, and quiz progress records.",
)
async def delete_user(user_id: str, current_user: dict = Depends(auth_services.get_current_user)):
    return await auth_services.UserService.delete_user(user_id, current_user)


@app.get(
    "/users/{user_id}/achievements",
    tags=["Achievements"],
    summary="List user achievements",
    description="Returns milestone rewards and completion certificates for a learner, optionally filtered by course.",
)
async def get_user_achievements(
    user_id: str,
    courseSlug: Optional[str] = None,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await achievement_services.AchievementService.get_user_achievements(user_id, courseSlug)


@app.post(
    "/users/{user_id}/courses",
    status_code=201,
    tags=["Course Enrollment"],
    summary="Enroll a user in a course",
    description="Adds a course enrollment record for the specified user.",
)
async def enroll_course(
    user_id: str,
    payload: CourseEnroll,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin"})
    return await course_services.CourseService.enroll_course(user_id, payload)


@app.get(
    "/users/{user_id}/courses",
    tags=["Course Enrollment"],
    summary="List a user's courses",
    description="Returns all course enrollments and progress records for a specific user.",
)
async def get_user_courses(
    user_id: str,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await course_services.CourseService.get_user_courses(user_id)


@app.get(
    "/users/{user_id}/courses/{course_slug}",
    tags=["Course Enrollment"],
    summary="Get user course progress",
    description="Returns the detailed progress state for one enrolled course belonging to a user.",
)
async def get_user_course_progress(
    user_id: str,
    course_slug: str,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await course_services.CourseService.get_user_course_progress(user_id, course_slug)


@app.patch(
    "/users/{user_id}/courses/{course_slug}/progress",
    tags=["Course Enrollment"],
    summary="Update course progress",
    description="Updates progress and completion state for a user's enrolled course.",
)
async def update_course_progress(
    user_id: str,
    course_slug: str,
    payload: CourseProgressUpdate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await course_services.CourseService.update_course_progress(user_id, course_slug, payload)


@app.post(
    "/courses/catalog",
    status_code=201,
    tags=["Course Catalog"],
    summary="Create a catalog course",
    description="Creates a new course catalog entry for admins and instructors.",
)
async def create_course_catalog(
    payload: CourseCatalogCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await course_services.CourseCatalogService.create_course_catalog(payload)


@app.get(
    "/courses/catalog",
    tags=["Course Catalog"],
    summary="List catalog courses",
    description="Returns catalog courses with optional category, difficulty, and free-text search filters.",
)
async def get_course_catalog(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
):
    return await course_services.CourseCatalogService.get_course_catalog(
        category=category,
        difficulty=difficulty,
        search=search,
    )


@app.get(
    "/courses/catalog/stats",
    tags=["Course Catalog"],
    summary="Get catalog statistics",
    description="Returns aggregate statistics for the course catalog.",
)
async def get_course_catalog_stats():
    return await course_services.CourseCatalogService.get_course_catalog_stats()


@app.get(
    "/courses/catalog/{slug}",
    tags=["Course Catalog"],
    summary="Get a catalog course",
    description="Returns a single course catalog entry by its slug.",
)
async def get_course_by_slug(slug: str):
    return await course_services.CourseCatalogService.get_course_by_slug(slug)


@app.put(
    "/courses/catalog/{slug}",
    tags=["Course Catalog"],
    summary="Update a catalog course",
    description="Replaces the stored details of an existing catalog course.",
)
async def update_course_catalog(
    slug: str,
    payload: CourseCatalogCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await course_services.CourseCatalogService.update_course_catalog(slug, payload)


@app.delete(
    "/courses/catalog/{slug}",
    tags=["Course Catalog"],
    summary="Delete a catalog course",
    description="Removes a course catalog entry identified by slug.",
)
async def delete_course_catalog(
    slug: str,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await course_services.CourseCatalogService.delete_course_catalog(slug)


@app.get(
    "/courses/{course_slug}/enrollments",
    tags=["Course Catalog"],
    summary="Get course enrollments",
    description="Returns a limited list of users enrolled in the specified course.",
)
async def get_course_enrollments(course_slug: str, limit: int = 10):
    return await course_services.CourseCatalogService.get_course_enrollments(course_slug, limit)


@app.get(
    "/courses/catalog/{slug}/curriculum",
    tags=["Curriculum"],
    summary="Get course curriculum",
    description="Returns the curriculum structure for a course, including modules and milestone projects.",
)
async def get_course_curriculum(slug: str):
    return await content_services.ContentService.get_course_curriculum(slug)


@app.get(
    "/lessons/library",
    tags=["Lesson Library"],
    summary="List lesson library items",
    description="Returns published course-linked sub-lessons and whether the current user can open them from an enrolled course.",
)
async def get_lesson_library(current_user: Optional[dict] = Depends(auth_services.get_optional_user)):
    return await lesson_library_services.LessonLibraryService.get_library(current_user)


@app.put(
    "/courses/catalog/{slug}/curriculum",
    tags=["Curriculum"],
    summary="Upsert course curriculum",
    description="Creates or replaces the curriculum structure for a course catalog entry.",
)
async def update_course_curriculum(
    slug: str,
    payload: CourseCurriculumUpsert,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    updated_by = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user["email"]
    return await content_services.ContentService.upsert_course_curriculum(slug, payload, updated_by)


@app.post(
    "/content/intake",
    tags=["Content Intake"],
    summary="Ingest uploaded learning content",
    description="Uploads a source document and lets the backend parse it into course content, lesson content, or question-bank records using the agentic ingestion workflow.",
)
async def ingest_learning_content(
    intent: str = Form(...),
    courseSlug: Optional[str] = Form(None),
    instructions: str = Form(""),
    sourceFile: UploadFile = File(...),
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await content_intake_services.ContentIntakeService.ingest_upload(
        current_user,
        intent=intent,
        source_file=sourceFile,
        course_slug=courseSlug,
        instructions=instructions,
    )


@app.post(
    "/content/intake/sessions/upload",
    tags=["Content Intake"],
    summary="Upload and scan source material",
    description="Stores the uploaded source, parses it, and creates a staged content-generation session with a proposed course plan before any module generation is performed.",
)
async def upload_content_generation_session(
    courseSlug: Optional[str] = Form(None),
    instructions: str = Form(""),
    sourceFile: UploadFile = File(...),
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await content_intake_services.ContentIntakeService.start_generation_session(
        current_user,
        source_file=sourceFile,
        course_slug=courseSlug,
        instructions=instructions,
    )


@app.get(
    "/content/intake/sessions/{session_id}",
    tags=["Content Intake"],
    summary="Get staged content-generation session",
    description="Returns the stored scan plan, linked course state, and generated progress for a previously uploaded content-generation session.",
)
async def get_content_generation_session(
    session_id: str,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await content_intake_services.ContentIntakeService.get_generation_session(session_id, current_user)


@app.post(
    "/content/intake/sessions/{session_id}/actions",
    tags=["Content Intake"],
    summary="Run a staged generation action",
    description="Runs one explicit instructor-approved generation step such as creating a course shell, generating one module, or generating questions for a module.",
)
async def run_content_generation_action(
    session_id: str,
    payload: ContentGenerationActionRequest,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await content_intake_services.ContentIntakeService.run_generation_action(
        session_id,
        current_user,
        action_type=payload.actionType,
        module_order=payload.moduleOrder,
        question_count=payload.questionCount,
        instructions=payload.instructions or "",
    )


@app.get(
    "/quizzes",
    tags=["Quizzes"],
    summary="List quizzes",
    description="Returns the quizzes currently available in the platform.",
)
async def get_quizzes():
    return await quiz_services.QuizService.get_quizzes()


@app.post(
    "/quizzes/{quiz_id}/questions",
    status_code=201,
    tags=["Question Bank"],
    summary="Create a question for a quiz",
    description="Creates a new question and associates it with the quiz identified in the path.",
)
async def create_question_with_quiz_path(
    quiz_id: str,
    payload: QuestionCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    authored_payload = payload.copy(update={"quizId": quiz_id})
    created_by = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user["email"]
    return await quiz_services.QuizService.create_question(authored_payload, created_by)


@app.get(
    "/quizzes/{quiz_id}/questions",
    tags=["Quizzes"],
    summary="Get quiz questions",
    description="Returns all questions attached to a specific quiz.",
)
async def get_quiz_questions(quiz_id: str):
    return await quiz_services.QuizService.get_quiz_questions(quiz_id)


@app.get(
    "/quizzes/questions/all",
    tags=["Quizzes"],
    summary="List all quiz questions",
    description="Returns all quiz questions across the platform without quiz filtering.",
)
async def get_all_quiz_questions():
    return await quiz_services.QuizService.get_all_quiz_questions()


@app.get(
    "/questions",
    tags=["Question Bank"],
    summary="Get question bank",
    description="Returns the full question bank for question management interfaces.",
)
async def get_question_bank(current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor"))):
    return await quiz_services.QuizService.get_question_bank()


@app.post(
    "/questions",
    status_code=201,
    tags=["Question Bank"],
    summary="Create a question",
    description="Creates a new question in the shared question bank.",
)
async def create_question(
    payload: QuestionCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    created_by = f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or current_user["email"]
    return await quiz_services.QuizService.create_question(payload, created_by)


@app.put(
    "/questions/{question_id}",
    tags=["Question Bank"],
    summary="Update a question",
    description="Replaces the stored details of a question in the question bank.",
)
async def update_question(
    question_id: str,
    payload: QuestionCreate,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await quiz_services.QuizService.update_question(question_id, payload)


@app.delete(
    "/questions/{question_id}",
    tags=["Question Bank"],
    summary="Delete a question",
    description="Removes a question from the question bank.",
)
async def delete_question(
    question_id: str,
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await quiz_services.QuizService.delete_question(question_id)


@app.post(
    "/users/{user_id}/quizzes/attempt",
    status_code=201,
    tags=["Quizzes"],
    summary="Submit quiz attempt",
    description="Stores a learner's quiz attempt and score for a given user.",
)
async def submit_quiz_attempt(
    user_id: str,
    payload: QuizAttemptCreate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await quiz_services.QuizService.submit_quiz_attempt(user_id, payload)


@app.get(
    "/users/{user_id}/quizzes",
    tags=["Quizzes"],
    summary="Get user quiz attempts",
    description="Returns quiz attempts recorded for a specific user.",
)
async def get_user_quiz_attempts(
    user_id: str,
    current_user: dict = Depends(auth_services.get_current_user),
):
    auth_services.ensure_self_or_roles(current_user, user_id, {"Admin", "Instructor"})
    return await quiz_services.QuizService.get_user_quiz_attempts(user_id)


@app.get(
    "/stats",
    tags=["Analytics"],
    summary="Get dashboard statistics",
    description="Returns top-level administrative statistics used on the dashboard.",
)
async def get_admin_stats(current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor"))):
    return await admin_services.AdminService.get_stats()


@app.get(
    "/activity",
    tags=["Analytics"],
    summary="Get recent activity",
    description="Returns recent platform activity for administrative dashboards.",
)
async def get_recent_activity(current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor"))):
    return await admin_services.AdminService.get_recent_activity()


@app.get(
    "/charts",
    tags=["Analytics"],
    summary="Get chart data",
    description="Returns aggregated analytics data for the requested dashboard period.",
)
async def get_chart_data(
    period: str = "7d",
    current_user: dict = Depends(auth_services.require_roles("Admin", "Instructor")),
):
    return await admin_services.AdminService.get_chart_data(period)


@app.get(
    "/agents/catalog",
    tags=["Agents"],
    summary="List available agent templates",
    description="Returns the agent types the current user can request based on account role.",
)
async def get_agent_catalog(current_user: dict = Depends(auth_services.get_current_user)):
    return await agent_services.AgentService.get_catalog(current_user)


@app.post(
    "/agents/requests",
    status_code=201,
    tags=["Agents"],
    summary="Request an agent assignment",
    description="Creates an approval request for an agent assigned to the current user.",
)
async def create_agent_request(
    payload: AgentRequestCreate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.create_request(payload, current_user)


@app.get(
    "/agents/assignments",
    tags=["Agents"],
    summary="List agent assignments",
    description="Returns agent requests and approved assignments visible to the current user.",
)
async def list_agent_assignments(
    status: Optional[str] = None,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.list_assignments(current_user, status)


@app.patch(
    "/agents/requests/{assignment_id}",
    tags=["Agents"],
    summary="Approve or reject an agent request",
    description="Lets admins review agent requests and mark them approved or rejected.",
)
async def update_agent_request(
    assignment_id: str,
    payload: AgentApprovalUpdate,
    current_user: dict = Depends(auth_services.require_roles("Admin")),
):
    return await agent_services.AgentService.update_request_status(assignment_id, payload, current_user)


@app.post(
    "/agents/threads",
    status_code=201,
    tags=["Agents"],
    summary="Create an agent chat thread",
    description="Starts a new chat thread for an approved agent assignment.",
)
async def create_agent_thread(
    payload: AgentThreadCreate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.create_thread(payload, current_user)


@app.get(
    "/agents/threads",
    tags=["Agents"],
    summary="List agent chat threads",
    description="Returns chat threads that belong to the current user or all threads for admins.",
)
async def list_agent_threads(
    assignmentId: Optional[str] = None,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.list_threads(current_user, assignmentId)


@app.get(
    "/agents/artifacts",
    tags=["Agents"],
    summary="List agent artifacts",
    description="Returns saved agent outputs such as curriculum drafts and lesson-planning notes.",
)
async def list_agent_artifacts(
    assignmentId: Optional[str] = None,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.list_artifacts(current_user, assignmentId)


@app.get(
    "/agents/threads/{thread_id}",
    tags=["Agents"],
    summary="Get one agent chat thread",
    description="Returns a thread with all user and assistant messages in chronological order.",
)
async def get_agent_thread(
    thread_id: str,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.get_thread(thread_id, current_user)


@app.post(
    "/agents/threads/{thread_id}/messages",
    status_code=201,
    tags=["Agents"],
    summary="Send a message to an agent",
    description="Adds a user message to the thread and returns the assistant response.",
)
async def post_agent_message(
    thread_id: str,
    payload: AgentMessageCreate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.post_message(thread_id, payload, current_user)


@app.post(
    "/agents/assignments/{assignment_id}/actions",
    status_code=201,
    tags=["Agents"],
    summary="Run a safe agent action",
    description="Runs an approved agent action such as creating a course shell, drafting curriculum, applying curriculum, or saving planning notes.",
)
async def run_agent_action(
    assignment_id: str,
    payload: AgentActionCreate,
    current_user: dict = Depends(auth_services.get_current_user),
):
    return await agent_services.AgentService.run_action(assignment_id, payload, current_user)
