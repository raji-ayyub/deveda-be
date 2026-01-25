# app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from services import auth_services, course_services, quiz_services, game_services
from schemas.schemas import (
    UserCreate, UserLogin, UserUpdate, UserPatch,
    CourseEnroll, CourseCatalogCreate, CourseProgressUpdate,
    QuizAttemptCreate, QuestionCreate
)

app = FastAPI(title="Learning Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Learning Platform API up and running"}

# Auth Routes
@app.post("/register", status_code=201)
async def register_user(payload: UserCreate):
    return await auth_services.AuthService.register_user(payload)

@app.post("/login")
async def login_user(payload: UserLogin):
    return await auth_services.AuthService.login_user(payload)

# User Routes
@app.get("/users")
async def get_all_users():
    return await auth_services.UserService.get_all_users()

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    return await auth_services.UserService.get_user(user_id)

@app.put("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate):
    return await auth_services.UserService.update_user(user_id, payload)

@app.patch("/users/{user_id}")
async def patch_user(user_id: str, payload: UserPatch):
    return await auth_services.UserService.patch_user(user_id, payload)

@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str):
    await auth_services.UserService.delete_user(user_id)

# Course Enrollment Routes
@app.post("/users/{user_id}/courses", status_code=201)
async def enroll_course(user_id: str, payload: CourseEnroll):
    return await course_services.CourseService.enroll_course(user_id, payload)

@app.get("/users/{user_id}/courses")
async def get_user_courses(user_id: str):
    return await course_services.CourseService.get_user_courses(user_id)

@app.get("/users/{user_id}/courses/{course_slug}")
async def get_user_course_progress(user_id: str, course_slug: str):
    return await course_services.CourseService.get_user_course_progress(user_id, course_slug)

@app.patch("/users/{user_id}/courses/{course_slug}/progress")
async def update_course_progress(user_id: str, course_slug: str, payload: CourseProgressUpdate):
    return await course_services.CourseService.update_course_progress(user_id, course_slug, payload)

# Course Catalog Routes
@app.post("/courses/catalog", status_code=201)
async def create_course_catalog(payload: CourseCatalogCreate):
    return await course_services.CourseCatalogService.create_course_catalog(payload)

@app.get("/courses/catalog")
async def get_course_catalog(
    category: str = None,
    difficulty: str = None,
    search: str = None
):
    return await course_services.CourseCatalogService.get_course_catalog(
        category=category,
        difficulty=difficulty,
        search=search
    )

@app.get("/courses/catalog/{slug}")
async def get_course_by_slug(slug: str):
    return await course_services.CourseCatalogService.get_course_by_slug(slug)

@app.put("/courses/catalog/{slug}")
async def update_course_catalog(slug: str, payload: CourseCatalogCreate):
    return await course_services.CourseCatalogService.update_course_catalog(slug, payload)

@app.delete("/courses/catalog/{slug}")
async def delete_course_catalog(slug: str):
    return await course_services.CourseCatalogService.delete_course_catalog(slug)

@app.get("/courses/catalog/stats")
async def get_course_catalog_stats():
    return await course_services.CourseCatalogService.get_course_catalog_stats()

@app.get("/courses/{course_slug}/enrollments")
async def get_course_enrollments(course_slug: str, limit: int = 10):
    return await course_services.CourseCatalogService.get_course_enrollments(course_slug, limit)

# Quiz Routes
@app.post("/quizzes/{quiz_id}/questions", status_code=201)
async def create_question(quiz_id: str, payload: QuestionCreate):
    return await quiz_services.QuizService.create_question(quiz_id, payload)

@app.get("/quizzes/{quiz_id}/questions")
async def get_quiz_questions(quiz_id: str):
    return await quiz_services.QuizService.get_quiz_questions(quiz_id)

@app.get("/quizzes/questions/all")
async def get_all_quiz_questions():
    return await quiz_services.QuizService.get_all_quiz_questions()

@app.post("/users/{user_id}/quizzes/attempt", status_code=201)
async def submit_quiz_attempt(user_id: str, payload: QuizAttemptCreate):
    return await quiz_services.QuizService.submit_quiz_attempt(user_id, payload)

@app.get("/users/{user_id}/quizzes")
async def get_user_quiz_attempts(user_id: str):
    return await quiz_services.QuizService.get_user_quiz_attempts(user_id)



@app.get("/users/{user_id}/games")
async def get_game_progress(user_id: str):
    return await game_services.GameService.get_game_progress(user_id)

@app.post("/users/{user_id}/games/{game_id}/progress")
async def update_game_progress(
    user_id: str, 
    game_id: str,
    level: int,
    xp: int
):
    return await game_services.GameService.update_game_progress(user_id, game_id, level, xp)