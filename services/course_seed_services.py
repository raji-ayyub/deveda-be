from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from database.database import course_catalog_collection, course_curricula_collection, quiz_questions_collection
from services.lesson_library_services import LessonLibraryService

SEED_AUTHOR = "Deveda Milestone Studio"
COURSE_SLUG = "frontend-milestone-blank-file-to-live-url"
COURSE_TITLE = "Frontend Milestone: Blank File to Live URL"


def _lesson(
    *,
    title: str,
    slug: str,
    summary: str,
    duration: int,
    objectives: list[str],
    takeaways: list[str],
    flow: list[str],
    markdown: str,
    practice: str,
    visual: str = "",
    content_type: str = "lesson",
    playground: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "slug": slug,
        "libraryLessonSlug": slug,
        "source": "seed",
        "generationStatus": "generated",
        "summary": summary,
        "durationMinutes": duration,
        "contentType": content_type,
        "quizId": None,
        "quizTitle": None,
        "learningObjectives": objectives,
        "keyTakeaways": takeaways,
        "learningFlow": flow,
        "contentMarkdown": markdown,
        "visualAidMarkdown": visual,
        "practicePrompt": practice,
        "instructorNotes": "Seeded milestone lesson.",
    }
    if playground is not None:
        payload["playground"] = playground
    return payload


def _question(question: str, options: list[str], answer: str, explanation: str, difficulty: str = "Medium") -> dict[str, Any]:
    return {
        "question": question,
        "options": options,
        "correct_answer": answer,
        "explanation": explanation,
        "points": 1,
        "question_type": "multiple_choice",
        "difficulty": difficulty,
        "is_active": True,
        "time_limit": 75,
    }


def _web_playground(instructions: str, html: str, css: str, js: str, checks: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "mode": "web",
        "instructions": instructions,
        "starterHtml": html,
        "starterCss": css,
        "starterJs": js,
        "checks": checks,
    }


def _js_playground(instructions: str, js: str, checks: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "mode": "javascript",
        "instructions": instructions,
        "starterHtml": "",
        "starterCss": "",
        "starterJs": js,
        "checks": checks,
    }


COURSE_CURRICULUM_TEMPLATE: dict[str, Any] = {
    "overview": (
        "This milestone validates the move from blank files to a polished live frontend project. "
        "It blends HTML structure, CSS layout, JavaScript logic, API work, GitHub workflow, and Vercel deployment."
    ),
    "learning_flow": [
        "Build clear structure first, then responsive layout.",
        "Move from static markup into JavaScript logic and DOM rendering.",
        "Finish with live data, deployment, and a presentable milestone showcase.",
    ],
    "visual_aid_markdown": (
        "## Roadmap\n"
        "`Semantic scaffold` -> `Responsive layout` -> `JavaScript logic` -> `Live data` -> `GitHub` -> `Vercel`\n\n"
        "The milestone is complete when the learner can share both the live URL and the repository."
    ),
    "modules": [
        {
            "title": "Structure and Layout Foundations",
            "description": "Turn an idea into a clean HTML and CSS project with strong layout decisions.",
            "order": 1,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Layout and styling quiz",
            "assessmentQuizId": f"{COURSE_SLUG}-layout-and-styling-quiz",
            "lessons": [
                _lesson(
                    title="Plan a semantic project scaffold",
                    slug=f"{COURSE_SLUG}-semantic-project-scaffold",
                    summary="Set up a page with meaningful sections before styling it.",
                    duration=20,
                    objectives=["Choose semantic page sections.", "Create clean styling hooks.", "Explain the page structure clearly."],
                    takeaways=["Strong markup makes styling easier.", "Semantic structure reduces messy rewrites."],
                    flow=["Outline the page areas.", "Write the HTML scaffold.", "Review before styling."],
                    markdown="# Plan a semantic scaffold\n\nUse meaningful HTML before worrying about visuals. Clear structure makes styling and scripting calmer later.",
                    visual="## Visual aid\n`Meaning` -> `Structure` -> `Style hooks`",
                    practice="Turn one student-project idea into a semantic page shell before adding CSS.",
                    playground=_web_playground(
                        "Create a semantic page shell with a header, main area, and footer.",
                        "<header><h1>Milestone Project</h1></header>\n<main><section class=\"hero\"></section></main>\n<footer></footer>",
                        "body { margin: 0; font-family: 'Segoe UI', sans-serif; }",
                        "",
                        [
                            {"label": "Use a header element", "type": "includes", "target": "html", "value": "<header"},
                            {"label": "Add a main area", "type": "includes", "target": "html", "value": "<main"},
                            {"label": "Keep a hero section hook", "type": "includes", "target": "html", "value": "class=\"hero\""},
                        ],
                    ),
                ),
                _lesson(
                    title="Build responsive sections with Flexbox",
                    slug=f"{COURSE_SLUG}-responsive-flexbox-sections",
                    summary="Use Flexbox to arrange related content cleanly across screen sizes.",
                    duration=30,
                    objectives=["Use a flex parent intentionally.", "Control spacing with gap and wrap.", "Adjust alignment without brittle hacks."],
                    takeaways=["Flexbox is ideal for one-dimensional layout.", "Parent layout rules create cleaner sections."],
                    flow=["Identify the parent container.", "Apply flex rules.", "Test the layout at smaller widths."],
                    markdown="# Build responsive sections with Flexbox\n\nStart with the container, not the children. Gap, alignment, and wrapping should be intentional.",
                    visual="## Visual aid\n`Parent container` -> `Flex alignment` -> `Responsive section`",
                    practice="Convert a plain list of project cards into a responsive card row that wraps cleanly.",
                    playground=_web_playground(
                        "Build a wrapping card layout with Flexbox.",
                        "<section class=\"card-grid\">\n  <article class=\"card\">HTML</article>\n  <article class=\"card\">CSS</article>\n  <article class=\"card\">JavaScript</article>\n</section>",
                        ".card-grid {\n  display: flex;\n}\n\n.card {\n  padding: 1rem;\n  border-radius: 1rem;\n  background: white;\n}\n",
                        "",
                        [
                            {"label": "Use display flex", "type": "includes", "target": "css", "value": "display: flex"},
                            {"label": "Add gap spacing", "type": "includes", "target": "css", "value": "gap"},
                            {"label": "Allow wrapping", "type": "includes", "target": "css", "value": "wrap"},
                        ],
                    ),
                ),
                _lesson(
                    title="Link styles and scripts cleanly",
                    slug=f"{COURSE_SLUG}-link-styles-and-scripts",
                    summary="Keep HTML, CSS, and JavaScript in separate files and wire them correctly.",
                    duration=20,
                    objectives=["Link CSS in the right place.", "Load JavaScript intentionally.", "Verify each file is connected."],
                    takeaways=["Project structure is part of professional workflow.", "Broken links are easy to catch with simple checks."],
                    flow=["Create the file structure.", "Link the stylesheet.", "Connect the script and verify all three files."],
                    markdown="# Link styles and scripts cleanly\n\nA tidy project is easier to debug, review, and deploy. File organization is part of the milestone.",
                    visual="## Visual aid\n`HTML` -> `External CSS` -> `External JavaScript`",
                    practice="Create `index.html`, `styles.css`, and `app.js`, then prove all three are connected by editing each one once.",
                ),
            ],
        },
        {
            "title": "JavaScript Logic and Live Interfaces",
            "description": "Move from static pages to interfaces powered by reusable logic and DOM updates.",
            "order": 2,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "JavaScript and DOM quiz",
            "assessmentQuizId": f"{COURSE_SLUG}-javascript-and-dom-quiz",
            "lessons": [
                _lesson(
                    title="Write reusable functions with parameters",
                    slug=f"{COURSE_SLUG}-functions-with-parameters",
                    summary="Package repeated logic into functions that can handle different inputs.",
                    duration=25,
                    objectives=["Name a function clearly.", "Use parameters to change behavior.", "Test one function with multiple values."],
                    takeaways=["Functions reduce repetition.", "Parameters make code reusable."],
                    flow=["Spot repeated logic.", "Move it into a function.", "Pass changing values as parameters."],
                    markdown="# Write reusable functions\n\nReusable code is one of the first signs that the learner is moving beyond copy-paste scripting.",
                    visual="## Visual aid\n`Repeated task` -> `Named function` -> `Different inputs`",
                    practice="Create a function that formats a project summary and call it with at least three different values.",
                    playground=_js_playground(
                        "Write a function that receives a learner name and project title, then logs a formatted summary.",
                        "function formatProject(name, title) {\n  return `${name} built ${title}`;\n}\n\nconsole.log(formatProject('Zara', 'Portfolio Card'));\n",
                        [
                            {"label": "Use a function", "type": "includes", "target": "js", "value": "function"},
                            {"label": "Accept parameters", "type": "includes", "target": "js", "value": "("},
                            {"label": "Log a result", "type": "includes", "target": "js", "value": "console.log"},
                        ],
                    ),
                ),
                _lesson(
                    title="Model data with arrays and objects",
                    slug=f"{COURSE_SLUG}-arrays-and-objects",
                    summary="Organize information so the interface has clean data to work with.",
                    duration=25,
                    objectives=["Choose between arrays and objects.", "Store repeated records clearly.", "Read properties from a data structure."],
                    takeaways=["Arrays hold many similar items.", "Objects hold named properties for one item."],
                    flow=["List the needed data.", "Shape one object.", "Collect several objects in an array."],
                    markdown="# Model data with arrays and objects\n\nGood rendering becomes easier when the data shape matches the story the page needs to tell.",
                    visual="## Visual aid\n`One record` -> `Object`\n`Many records` -> `Array`",
                    practice="Create an array of three project objects and decide which fields the DOM will display.",
                ),
                _lesson(
                    title="Render data into the DOM",
                    slug=f"{COURSE_SLUG}-dom-rendering",
                    summary="Turn stored data into visible content on the page.",
                    duration=35,
                    objectives=["Pick a DOM render target.", "Loop through stored data.", "Render repeated UI content clearly."],
                    takeaways=["DOM rendering connects logic to what the user sees.", "Clean data shapes make rendering easier."],
                    flow=["Choose the container.", "Read the data.", "Build the output.", "Inject it into the page."],
                    markdown="# Render data into the DOM\n\nRendering is the bridge between stored JavaScript data and visible interface output.",
                    visual="## Visual aid\n`Array of records` -> `Render function` -> `Visible cards`",
                    practice="Render a list of project summaries into card elements and confirm the DOM updates when the data changes.",
                    playground=_web_playground(
                        "Render a small project list into the page with JavaScript.",
                        "<section>\n  <h1>Projects</h1>\n  <div id=\"project-list\"></div>\n</section>",
                        "#project-list {\n  display: grid;\n  gap: 12px;\n}\n\n.project-card {\n  padding: 12px;\n  border-radius: 12px;\n  background: #eff6ff;\n}\n",
                        "const projects = [\n  { title: 'Landing Page', status: 'Live' },\n  { title: 'Quiz App', status: 'In progress' },\n];\n\nconst list = document.getElementById('project-list');\nlist.innerHTML = projects.map((project) => `<article class=\"project-card\"><h2>${project.title}</h2><p>${project.status}</p></article>`).join('');\n",
                        [
                            {"label": "Target the project list", "type": "includes", "target": "js", "value": "project-list"},
                            {"label": "Loop through data", "type": "includes", "target": "js", "value": ".map("},
                            {"label": "Render project-card markup", "type": "includes", "target": "js", "value": "project-card"},
                        ],
                    ),
                ),
            ],
        },
        {
            "title": "APIs, Workflow, and Launch",
            "description": "Fetch external data, manage the repo, and ship a live milestone project with confidence.",
            "order": 3,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Final milestone test",
            "assessmentQuizId": f"{COURSE_SLUG}-final-milestone-test",
            "lessons": [
                _lesson(
                    title="Fetch live data with async and await",
                    slug=f"{COURSE_SLUG}-async-await-api-fetching",
                    summary="Call an API, wait for the response, and use the result in the interface.",
                    duration=35,
                    objectives=["Explain async and await simply.", "Fetch data and parse JSON.", "Connect API data to an interface."],
                    takeaways=["Async and await make request flow easier to read.", "Fetched data must still be rendered clearly."],
                    flow=["Choose the endpoint.", "Fetch the data.", "Parse the JSON.", "Render useful fields."],
                    markdown="# Fetch live data with async and await\n\nThis lesson turns delayed data into a readable, step-by-step workflow.",
                    visual="## Visual aid\n`Request` -> `await response` -> `await json` -> `render`",
                    practice="Fetch a small public JSON dataset and render two useful fields into the page.",
                    playground=_js_playground(
                        "Write an async function that fetches user data and logs one field.",
                        "async function loadProjects() {\n  const response = await fetch('https://jsonplaceholder.typicode.com/users');\n  const data = await response.json();\n  console.log(data[0].name);\n}\n\nloadProjects();\n",
                        [
                            {"label": "Use async function syntax", "type": "includes", "target": "js", "value": "async function"},
                            {"label": "Await the fetch call", "type": "includes", "target": "js", "value": "await fetch"},
                            {"label": "Parse JSON", "type": "includes", "target": "js", "value": "response.json"},
                        ],
                    ),
                ),
                _lesson(
                    title="Track progress with Git and GitHub",
                    slug=f"{COURSE_SLUG}-git-and-github-workflow",
                    summary="Save project changes in meaningful checkpoints and push them to GitHub.",
                    duration=20,
                    objectives=["Explain why commits matter.", "Describe a simple local-to-GitHub flow.", "Recognize a useful beginner commit."],
                    takeaways=["Version control is part of professional workflow.", "GitHub makes work visible and reviewable."],
                    flow=["Stage one clear change.", "Write a meaningful commit.", "Push it to the remote repo."],
                    markdown="# Track progress with Git and GitHub\n\nA milestone is stronger when the learner can show both the finished project and the build history behind it.",
                    visual="## Visual aid\n`Local change` -> `Commit` -> `GitHub history`",
                    practice="Create three milestone-sized commits: scaffold, styling pass, and JavaScript feature.",
                ),
                _lesson(
                    title="Deploy and verify on Vercel",
                    slug=f"{COURSE_SLUG}-deploy-and-verify-on-vercel",
                    summary="Publish the project and confirm the live version behaves as expected.",
                    duration=25,
                    objectives=["Describe what deployment changes.", "Connect a repo to Vercel.", "Verify the live result after launch."],
                    takeaways=["Deployment proves the project works beyond the local machine.", "A live URL is a strong milestone artifact."],
                    flow=["Connect the repo.", "Trigger deployment.", "Test the live URL.", "Fix and redeploy if needed."],
                    markdown="# Deploy and verify on Vercel\n\nA project becomes easier to share, review, and celebrate when it is live on the web.",
                    visual="## Visual aid\n`Repository` -> `Vercel deploy` -> `Live verification`",
                    practice="Deploy a small frontend project, then click through the main interface once to confirm it matches the local version.",
                ),
                _lesson(
                    title="Prepare the milestone showcase",
                    slug=f"{COURSE_SLUG}-milestone-showcase-project",
                    summary="Package the repository, live URL, and project explanation into a final milestone story.",
                    duration=30,
                    objectives=["Summarize what the project proves.", "Gather final milestone evidence.", "Reflect on the tools used in the build."],
                    takeaways=["Presentation is part of engineering communication.", "The repo, live URL, and reflection together make the milestone credible."],
                    flow=["Choose the project to present.", "List the technologies used.", "Attach the repo and live URL.", "Prepare a short walkthrough."],
                    markdown="# Prepare the milestone showcase\n\nFinishing the milestone means being able to explain the build, not just ship the code.",
                    visual="## Visual aid\n`Project summary` -> `Repository` -> `Live URL` -> `Reflection`",
                    practice="Write a short milestone summary that names the problem, the tools used, the live URL, and one improvement for later.",
                    content_type="project",
                ),
            ],
        },
    ],
    "milestone_projects": [
        {
            "title": "Milestone 1: Styled portfolio section",
            "description": "Build a semantic, responsive section with clear file organization.",
            "milestoneOrder": 1,
            "estimatedHours": 2,
            "deliverables": ["Semantic HTML scaffold", "Responsive Flexbox layout", "External files linked correctly"],
            "completionThreshold": 55,
        },
        {
            "title": "Milestone 2: Interactive data view",
            "description": "Create a small interface powered by reusable JavaScript and DOM rendering.",
            "milestoneOrder": 2,
            "estimatedHours": 3,
            "deliverables": ["Reusable functions", "Array or object driven rendering", "Visible DOM update"],
            "completionThreshold": 78,
        },
        {
            "title": "Milestone 3: Launch-ready showcase",
            "description": "Ship a live frontend project and package the proof points for review.",
            "milestoneOrder": 3,
            "estimatedHours": 4,
            "deliverables": ["GitHub repository", "Live Vercel deployment", "Short project walkthrough"],
            "completionThreshold": 95,
        },
    ],
}


QUIZ_BANK: dict[str, list[dict[str, Any]]] = {
    f"{COURSE_SLUG}-layout-and-styling-quiz": [
        _question(
            "Why is Flexbox a strong choice for arranging a row of cards?",
            [
                "It automatically creates a database for the cards",
                "It controls alignment and spacing along one main axis cleanly",
                "It replaces the need for HTML structure",
                "It only works on desktop screens",
            ],
            "It controls alignment and spacing along one main axis cleanly",
            "Flexbox is built for one-dimensional layout problems like aligned rows or columns.",
            "Easy",
        ),
        _question(
            "Where should an external stylesheet usually be linked in a basic HTML page?",
            [
                "Inside the footer",
                "Inside the body after the last section",
                "In the head of the document",
                "Inside the JavaScript file",
            ],
            "In the head of the document",
            "Linking CSS in the head lets the browser load styles as the document is parsed.",
            "Easy",
        ),
        _question(
            "What is the main reason to start a project with semantic HTML before styling?",
            [
                "It makes the page easier to structure, style, and maintain",
                "It removes the need for classes and ids completely",
                "It guarantees automatic deployment",
                "It replaces JavaScript logic",
            ],
            "It makes the page easier to structure, style, and maintain",
            "Semantic structure gives the rest of the project a cleaner foundation.",
            "Medium",
        ),
    ],
    f"{COURSE_SLUG}-javascript-and-dom-quiz": [
        _question(
            "What makes a function reusable?",
            [
                "It can run the same logic with different input values",
                "It is written inside an HTML comment",
                "It only works once before being deleted",
                "It replaces arrays and objects entirely",
            ],
            "It can run the same logic with different input values",
            "Reusable functions package logic once and change behavior through inputs.",
            "Easy",
        ),
        _question(
            "When storing several project cards with titles and descriptions, which structure is usually most practical?",
            [
                "An array of project objects",
                "One CSS rule",
                "A single string with every value mixed together",
                "A footer element",
            ],
            "An array of project objects",
            "An array lets you loop over multiple project records while each object stores one project's fields.",
            "Easy",
        ),
        _question(
            "What does DOM rendering mean in this course context?",
            [
                "Turning stored data into visible content on the page",
                "Saving Git commits to the terminal",
                "Compressing CSS into smaller files",
                "Deploying a project to a live host",
            ],
            "Turning stored data into visible content on the page",
            "Rendering is the step where JavaScript updates what the learner sees on screen.",
            "Medium",
        ),
    ],
    f"{COURSE_SLUG}-final-milestone-test": [
        _question(
            "Which evidence set best supports this milestone certification?",
            [
                "A live URL, a GitHub repository, and a short explanation of the build",
                "Only a screenshot of the homepage",
                "Only a JavaScript file copied into a message",
                "A list of technologies without a project",
            ],
            "A live URL, a GitHub repository, and a short explanation of the build",
            "The milestone is strongest when the learner can show the working result, the code, and the story behind it.",
            "Easy",
        ),
        _question(
            "What is the best next step after fetching JSON from an API for a frontend interface?",
            [
                "Render the needed fields into the DOM in a clear format",
                "Delete the data immediately",
                "Move the CSS into the JSON response",
                "Replace the HTML file with the API URL",
            ],
            "Render the needed fields into the DOM in a clear format",
            "Fetching is only part of the job. The interface still needs to show the result clearly.",
            "Medium",
        ),
        _question(
            "Which workflow shows the strongest launch discipline for this course?",
            [
                "Commit meaningful changes, push to GitHub, deploy, and verify the live result",
                "Build locally, skip commits, and share the unfinished link",
                "Deploy first and write the code later",
                "Wait to test until after the certificate is issued",
            ],
            "Commit meaningful changes, push to GitHub, deploy, and verify the live result",
            "The milestone emphasizes version control, shipping, and a final verification step.",
            "Medium",
        ),
    ],
}


def _curriculum_summary(curriculum: dict[str, Any]) -> dict[str, int]:
    modules = curriculum.get("modules", [])
    total_lessons = sum(len(module.get("lessons", [])) for module in modules)
    total_quizzes = sum(1 for module in modules if module.get("assessmentQuizId"))
    lesson_minutes = sum(
        int(lesson.get("durationMinutes") or 0)
        for module in modules
        for lesson in module.get("lessons", [])
    )
    milestone_minutes = sum(int(project.get("estimatedHours") or 0) * 60 for project in curriculum.get("milestone_projects", []))
    return {
        "total_lessons": total_lessons,
        "total_quizzes": total_quizzes,
        "duration": lesson_minutes + milestone_minutes,
    }


async def ensure_frontend_blank_file_milestone_seed() -> None:
    now = datetime.utcnow()
    summary = _curriculum_summary(COURSE_CURRICULUM_TEMPLATE)
    seeded_new_content = False

    existing_course = await course_catalog_collection.find_one({"slug": COURSE_SLUG})
    if not existing_course:
        course_document = {
            "slug": COURSE_SLUG,
            "title": COURSE_TITLE,
            "description": (
                "Validate the ability to structure, style, script, version, and deploy a real frontend project from scratch. "
                "This milestone mirrors the journey from blank files to a shareable live URL."
            ),
            "category": "Frontend Development",
            "difficulty": "Beginner",
            "duration": summary["duration"],
            "total_quizzes": summary["total_quizzes"],
            "total_lessons": summary["total_lessons"],
            "instructor": "Deveda Milestone Studio",
            "prerequisites": [],
            "tags": ["html", "css", "javascript", "dom", "apis", "git", "github", "vercel"],
            "thumbnail": "",
            "thumbnail_public_id": "",
            "created_at": now,
        }
        result = await course_catalog_collection.insert_one(course_document)
        course_document["_id"] = result.inserted_id
        existing_course = course_document
        seeded_new_content = True

    existing_curriculum = await course_curricula_collection.find_one({"course_slug": COURSE_SLUG})
    if not existing_curriculum:
        curriculum_document = deepcopy(COURSE_CURRICULUM_TEMPLATE)
        curriculum_document.update(
            {
                "course_slug": COURSE_SLUG,
                "updated_at": now,
                "updated_by": SEED_AUTHOR,
                "is_draft_scaffold": False,
            }
        )
        result = await course_curricula_collection.insert_one(curriculum_document)
        curriculum_document["_id"] = result.inserted_id
        existing_curriculum = curriculum_document
        seeded_new_content = True

    if existing_course and existing_curriculum:
        await LessonLibraryService.sync_course_lessons(existing_course, existing_curriculum, SEED_AUTHOR)

    if not seeded_new_content:
        return

    for quiz_id, questions in QUIZ_BANK.items():
        if await quiz_questions_collection.count_documents({"quiz_id": quiz_id}) > 0:
            continue

        created_at = datetime.utcnow()
        await quiz_questions_collection.insert_many(
            [
                {
                    "quiz_id": quiz_id,
                    "question": question["question"],
                    "options": question["options"],
                    "correct_answer": question["correct_answer"],
                    "explanation": question["explanation"],
                    "points": question["points"],
                    "question_type": question["question_type"],
                    "difficulty": question["difficulty"],
                    "is_active": question["is_active"],
                    "time_limit": question["time_limit"],
                    "created_by": SEED_AUTHOR,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
                for question in questions
            ]
        )
