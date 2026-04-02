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
    game_key: str | None = None,
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
    if game_key is not None:
        payload["gameKey"] = game_key
    if playground is not None:
        payload["playground"] = playground
    return payload


def _question(question: str, options: list[str], answer: str, explanation: str, difficulty: str = "Medium") -> dict[str, Any]:
    seeded_options = list(options)
    if answer in seeded_options and len(seeded_options) > 1:
        score = sum(ord(character) for character in f"{question}{answer}")
        target_index = score % len(seeded_options)
        if target_index == 0:
            target_index = (score % (len(seeded_options) - 1)) + 1
        current_index = seeded_options.index(answer)
        if current_index != target_index:
            seeded_options.pop(current_index)
            seeded_options.insert(target_index, answer)
    return {
        "question": question,
        "options": seeded_options,
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


BEGINNER_COURSE_SLUG = "frontend-development-beginner"
BEGINNER_COURSE_TITLE = "Frontend Development Beginner"
BEGINNER_SEED_AUTHOR = "Deveda Frontend Team"

BEGINNER_CURRICULUM_TEMPLATE: dict[str, Any] = {
    "overview": (
        "Frontend Development Beginner gives learners a real first path through HTML, CSS, responsive layout, "
        "and JavaScript basics. The course moves from page structure, to styling, to layout, to small interactions "
        "that prove the learner can build and explain a simple frontend project."
    ),
    "learning_flow": [
        "Start with semantic HTML and clean page structure before styling.",
        "Use CSS intentionally so spacing, hierarchy, and reusable classes stay readable.",
        "Introduce responsive layout patterns that hold together on smaller screens.",
        "Finish with small JavaScript interactions that connect data, events, and the DOM.",
    ],
    "visual_aid_markdown": (
        "## Course roadmap\n"
        "`HTML structure` -> `CSS styling` -> `Responsive layout` -> `JavaScript interaction`\n\n"
        "Each module ends with a short checkpoint quiz so the learner can confirm understanding before moving on."
    ),
    "modules": [
        {
            "title": "HTML Foundations and Page Structure",
            "description": "Learn how to structure a page with semantic HTML so later styling and scripting stay clear.",
            "order": 1,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "HTML foundations quiz",
            "assessmentQuizId": f"{BEGINNER_COURSE_SLUG}-html-foundations-quiz",
            "lessons": [
                _lesson(
                    title="Understand semantic HTML structure",
                    slug=f"{BEGINNER_COURSE_SLUG}-semantic-html-structure",
                    summary="Use meaningful tags like header, main, section, and footer to build readable page structure.",
                    duration=22,
                    objectives=["Identify when semantic tags improve clarity.", "Break a page into meaningful sections.", "Choose structure before adding style."],
                    takeaways=["Semantic HTML describes purpose, not appearance.", "A clear page outline makes later styling easier."],
                    flow=["List the major parts of the page.", "Choose semantic tags for each part.", "Review whether the structure reads clearly without CSS."],
                    markdown=(
                        "# Understand semantic HTML structure\n\n"
                        "HTML works best when the markup explains what each part of the page is doing. "
                        "A `header` introduces the page, `main` holds the primary content, and `footer` closes it out.\n\n"
                        "## Why this matters\n"
                        "When a page is structured well, CSS and JavaScript become easier to reason about. "
                        "You can find the right section faster, assign cleaner class names, and explain the page to someone else without guessing.\n\n"
                        "## Teaching sequence\n"
                        "1. Sketch the page areas in plain language.\n"
                        "2. Match those areas to semantic tags.\n"
                        "3. Add classes only where styling hooks are genuinely needed.\n"
                        "4. Read the HTML top to bottom and check whether it tells the story of the page."
                    ),
                    practice="Turn a simple landing page idea into a semantic scaffold using header, main, at least two sections, and footer.",
                    visual="## Visual aid\n`Page goal` -> `Semantic sections` -> `Clean structure`",
                    playground=_web_playground(
                        "Build a simple semantic page shell with a header, main area, and footer.",
                        "<header><h1>Frontend Starter</h1></header>\n<main>\n  <section class=\"hero\"></section>\n  <section class=\"features\"></section>\n</main>\n<footer></footer>",
                        "body { margin: 0; font-family: 'Segoe UI', sans-serif; }",
                        "",
                        [
                            {"label": "Use a header tag", "type": "includes", "target": "html", "value": "<header"},
                            {"label": "Use a main tag", "type": "includes", "target": "html", "value": "<main"},
                            {"label": "Include a footer", "type": "includes", "target": "html", "value": "<footer"},
                        ],
                    ),
                ),
                _lesson(
                    title="Work with text, links, and images",
                    slug=f"{BEGINNER_COURSE_SLUG}-text-links-and-images",
                    summary="Use headings, paragraphs, anchors, and images to communicate clearly inside a page.",
                    duration=20,
                    objectives=["Create readable text hierarchy with headings.", "Use links intentionally.", "Add images with useful supporting text."],
                    takeaways=["Content order shapes readability.", "Links and images should support the page goal, not distract from it."],
                    flow=["Choose the page message.", "Arrange headings and supporting text.", "Add a link and image that fit the same purpose."],
                    markdown=(
                        "# Work with text, links, and images\n\n"
                        "Frontend pages are not only layouts. They also communicate. "
                        "Good text hierarchy helps learners and users scan quickly, while links and images should feel intentional.\n\n"
                        "## What to focus on\n"
                        "- Use one clear main heading.\n"
                        "- Support it with short paragraphs.\n"
                        "- Add anchor text that explains where the link goes.\n"
                        "- Use image descriptions that still make sense if the image does not load.\n\n"
                        "The goal is to make the page understandable before any advanced styling is added."
                    ),
                    practice="Create a short hero section with one heading, a supporting paragraph, a call-to-action link, and one image.",
                    visual="## Visual aid\n`Heading` -> `Support text` -> `Action link` -> `Supporting image`",
                ),
                _lesson(
                    title="Build simple forms and grouped content",
                    slug=f"{BEGINNER_COURSE_SLUG}-forms-and-grouped-content",
                    summary="Use forms, labels, and grouped page sections to collect input and organize related content.",
                    duration=24,
                    objectives=["Associate labels with inputs clearly.", "Group related content into sections or cards.", "Explain what each form field is for."],
                    takeaways=["Forms should be readable before they are beautiful.", "Labels and grouping improve usability."],
                    flow=["Choose the information to collect.", "Create labeled inputs.", "Wrap related fields and content together cleanly."],
                    markdown=(
                        "# Build simple forms and grouped content\n\n"
                        "Forms are often a learner's first experience with interface structure that has both content and interaction. "
                        "A strong beginner form is clear, labeled, and easy to scan.\n\n"
                        "## Good beginner habits\n"
                        "1. Keep each field tied to one simple purpose.\n"
                        "2. Label the field so the learner knows what to enter.\n"
                        "3. Group related inputs together instead of scattering them across the page.\n"
                        "4. Finish with one obvious action button."
                    ),
                    practice="Create a basic contact or signup form with labels, two inputs, and a submit button inside a grouped section.",
                    visual="## Visual aid\n`Label` -> `Input` -> `Grouped section` -> `Submit action`",
                ),
            ],
        },
        {
            "title": "CSS Basics and Visual Styling",
            "description": "Learn how selectors, spacing, and reusable classes turn plain markup into a clear interface.",
            "order": 2,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "CSS basics quiz",
            "assessmentQuizId": f"{BEGINNER_COURSE_SLUG}-css-basics-quiz",
            "lessons": [
                _lesson(
                    title="Use selectors and the cascade intentionally",
                    slug=f"{BEGINNER_COURSE_SLUG}-selectors-and-cascade",
                    summary="Target the right elements and understand how CSS rules combine or override each other.",
                    duration=24,
                    objectives=["Differentiate between element, class, and id selectors.", "Explain what the cascade is doing.", "Choose reusable selectors over brittle styling."],
                    takeaways=["Selectors should be as simple as the job allows.", "The cascade is easier to manage when class names are purposeful."],
                    flow=["Choose the element to style.", "Pick the most reusable selector.", "Observe which rule wins and why."],
                    markdown=(
                        "# Use selectors and the cascade intentionally\n\n"
                        "CSS becomes frustrating when selectors are chosen reactively. "
                        "A better beginner habit is to style with clear classes and understand why one rule overrides another.\n\n"
                        "## Core idea\n"
                        "The cascade means multiple rules can target the same element. "
                        "Instead of fighting that, learn to read it: which selector is stronger, and which rule comes later?\n\n"
                        "That understanding reduces random trial and error."
                    ),
                    practice="Style a card title, body text, and action button with reusable classes instead of styling every tag globally.",
                    visual="## Visual aid\n`Selector choice` -> `Cascade decision` -> `Stable styles`",
                ),
                _lesson(
                    title="Control spacing with the box model",
                    slug=f"{BEGINNER_COURSE_SLUG}-box-model-spacing",
                    summary="Use margin, padding, width, and borders to create cleaner layouts and breathing room.",
                    duration=26,
                    objectives=["Explain the difference between margin and padding.", "Use spacing to separate content clearly.", "Recognize how width and borders affect layout."],
                    takeaways=["Spacing is part of clarity, not decoration.", "The box model explains why elements take up the space they do."],
                    flow=["Inspect the element box.", "Adjust padding for internal space.", "Use margin to separate elements from each other."],
                    markdown=(
                        "# Control spacing with the box model\n\n"
                        "Many beginner layout problems come from unclear spacing. "
                        "The box model gives you a mental map: content sits inside padding, borders wrap the content box, and margins push other elements away.\n\n"
                        "## A practical mindset\n"
                        "Ask whether the space should live inside the component or between components. "
                        "That single question helps you choose padding or margin more confidently."
                    ),
                    practice="Create a content card with padding inside the card and margin between cards so the difference feels obvious.",
                    visual="## Visual aid\n`Content` -> `Padding` -> `Border` -> `Margin`",
                    playground=_web_playground(
                        "Style a card so the spacing inside and outside the card is easy to see.",
                        "<article class=\"profile-card\">\n  <h2>Zara</h2>\n  <p>Frontend learner</p>\n</article>",
                        ".profile-card {\n  background: white;\n  border: 1px solid #cbd5e1;\n}\n",
                        "",
                        [
                            {"label": "Add padding to the card", "type": "includes", "target": "css", "value": "padding"},
                            {"label": "Add margin to the card", "type": "includes", "target": "css", "value": "margin"},
                            {"label": "Keep a border on the card", "type": "includes", "target": "css", "value": "border"},
                        ],
                    ),
                ),
                _lesson(
                    title="Style reusable interface components",
                    slug=f"{BEGINNER_COURSE_SLUG}-reusable-interface-components",
                    summary="Turn repeated UI elements like buttons and cards into reusable class-based components.",
                    duration=24,
                    objectives=["Identify repeated UI patterns.", "Create reusable classes for repeated elements.", "Keep visual rules consistent across similar components."],
                    takeaways=["Consistency improves design and maintainability.", "Reusable classes reduce duplicated CSS."],
                    flow=["Spot repeated elements.", "Create shared classes.", "Apply the same component styles in more than one place."],
                    markdown=(
                        "# Style reusable interface components\n\n"
                        "A beginner frontend project becomes more professional when the learner stops styling every element as a one-off. "
                        "Buttons, cards, and badges often repeat, so they deserve shared styling rules.\n\n"
                        "This creates consistency and lowers the cost of future edits."
                    ),
                    practice="Create a reusable `.btn` class and a `.card` class, then apply them to more than one part of the page.",
                    visual="## Visual aid\n`Repeated element` -> `Shared class` -> `Consistent UI`",
                ),
            ],
        },
        {
            "title": "Responsive Layout with Flexbox",
            "description": "Use layout rules that adapt well across screen sizes without relying on brittle positioning.",
            "order": 3,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Responsive layout quiz",
            "assessmentQuizId": f"{BEGINNER_COURSE_SLUG}-responsive-layout-quiz",
            "lessons": [
                _lesson(
                    title="Understand Flexbox containers and alignment",
                    slug=f"{BEGINNER_COURSE_SLUG}-flexbox-containers-and-alignment",
                    summary="Use Flexbox on the parent container to control direction, spacing, and alignment of child elements.",
                    duration=28,
                    objectives=["Recognize when Flexbox belongs on the parent.", "Use direction and alignment intentionally.", "Explain how the main axis affects layout choices."],
                    takeaways=["Flexbox is a parent-driven layout system.", "Alignment is easier when the container rules are clear."],
                    flow=["Identify the container.", "Apply display flex.", "Choose axis direction and alignment.", "Review the effect on the children."],
                    markdown=(
                        "# Understand Flexbox containers and alignment\n\n"
                        "Flexbox solves many beginner layout problems because it gives the parent container control over how children line up. "
                        "Instead of nudging each child individually, define the layout once at the container level.\n\n"
                        "## Key question\n"
                        "What should happen along the main axis: row or column? "
                        "Once that answer is clear, alignment becomes much easier to manage."
                    ),
                    practice="Place three cards inside a flex container and align them in a row with visible spacing.",
                    visual="## Visual aid\n`Parent container` -> `Main axis` -> `Aligned children`",
                    playground=_web_playground(
                        "Create a row of cards with Flexbox.",
                        "<section class=\"card-row\">\n  <article class=\"card\">HTML</article>\n  <article class=\"card\">CSS</article>\n  <article class=\"card\">JS</article>\n</section>",
                        ".card { padding: 1rem; background: white; border-radius: 1rem; }\n",
                        "",
                        [
                            {"label": "Use display flex", "type": "includes", "target": "css", "value": "display: flex"},
                            {"label": "Add gap spacing", "type": "includes", "target": "css", "value": "gap"},
                            {"label": "Target the card row", "type": "includes", "target": "css", "value": ".card-row"},
                        ],
                    ),
                ),
                _lesson(
                    title="Use wrapping, width, and spacing for smaller screens",
                    slug=f"{BEGINNER_COURSE_SLUG}-wrapping-width-and-spacing",
                    summary="Combine wrapping, widths, and spacing choices so rows still work when the screen gets tighter.",
                    duration=25,
                    objectives=["Allow layouts to wrap when space runs out.", "Use widths that leave room to breathe.", "Check how spacing behaves on narrower screens."],
                    takeaways=["Responsive layout is about adaptation, not perfection at one size.", "Wrap is often better than forcing everything onto one row."],
                    flow=["Start from a desktop row.", "Reduce the available width.", "Allow wrap and adjust widths if needed."],
                    markdown=(
                        "# Use wrapping, width, and spacing for smaller screens\n\n"
                        "A row that only works on a wide screen is not finished. "
                        "Responsive thinking means checking what happens when width shrinks and deciding whether cards should wrap, resize, or stack.\n\n"
                        "The goal is not fancy tricks. It is preserving readability."
                    ),
                    practice="Take a three-card row and make sure it wraps into a clean multi-line layout on narrow screens.",
                    visual="## Visual aid\n`Wide row` -> `Less space` -> `Wrap cleanly`",
                ),
                _lesson(
                    title="Build a responsive hero or feature section",
                    slug=f"{BEGINNER_COURSE_SLUG}-responsive-hero-section",
                    summary="Combine semantic HTML, CSS styling, and Flexbox to build one polished responsive section.",
                    duration=30,
                    objectives=["Combine structure and styling in one section.", "Use Flexbox to organize content blocks.", "Check the section on wide and narrow layouts."],
                    takeaways=["Responsive sections combine several earlier skills.", "One polished section is stronger than many unfinished parts."],
                    flow=["Write the section structure.", "Apply visual styles.", "Use Flexbox for layout.", "Review the section at smaller widths."],
                    markdown=(
                        "# Build a responsive hero or feature section\n\n"
                        "This lesson combines everything so far into one presentable UI block. "
                        "A strong beginner section has a clear heading, supporting text, a call to action, and layout that still reads well on smaller screens.\n\n"
                        "This is often the first moment learners see how HTML, CSS, and layout rules work together."
                    ),
                    practice="Build one responsive hero or feature section for a beginner portfolio, course page, or product teaser.",
                    visual="## Visual aid\n`Structure` -> `Style` -> `Flex layout` -> `Responsive review`",
                ),
            ],
        },
        {
            "title": "JavaScript Basics and Small Interactions",
            "description": "Use JavaScript to select elements, respond to user actions, and render small pieces of data into the page.",
            "order": 4,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "JavaScript basics quiz",
            "assessmentQuizId": f"{BEGINNER_COURSE_SLUG}-javascript-basics-quiz",
            "lessons": [
                _lesson(
                    title="Use variables and select DOM elements",
                    slug=f"{BEGINNER_COURSE_SLUG}-variables-and-dom-selection",
                    summary="Store values in variables and select page elements so JavaScript can work with the interface.",
                    duration=24,
                    objectives=["Store simple values in variables.", "Select DOM elements by id or class.", "Explain why the script needs a clear target element."],
                    takeaways=["Variables store values the script can reuse.", "DOM selection is the first bridge from JavaScript to the page."],
                    flow=["Store one useful value.", "Select one page element.", "Log or update it to confirm the script is connected."],
                    markdown=(
                        "# Use variables and select DOM elements\n\n"
                        "JavaScript becomes useful in the browser when it can both remember information and find the part of the page it needs to change. "
                        "Variables handle the first job. DOM selection handles the second.\n\n"
                        "Start small: store a value, select an element, then prove the connection with a simple update."
                    ),
                    practice="Select a button or heading from the page and update its text using a stored variable.",
                    visual="## Visual aid\n`Variable` -> `DOM target` -> `Visible update`",
                    playground=_web_playground(
                        "Update a heading on the page with JavaScript.",
                        "<section>\n  <h1 id=\"title\">Original title</h1>\n</section>",
                        "body { font-family: 'Segoe UI', sans-serif; padding: 24px; }",
                        "const titleText = 'Updated with JavaScript';\nconst title = document.getElementById('title');\nif (title) {\n  title.textContent = titleText;\n}\n",
                        [
                            {"label": "Store a variable", "type": "includes", "target": "js", "value": "const"},
                            {"label": "Select a DOM element", "type": "includes", "target": "js", "value": "getElementById"},
                            {"label": "Update visible text", "type": "includes", "target": "js", "value": "textContent"},
                        ],
                    ),
                ),
                _lesson(
                    title="Respond to click events with functions",
                    slug=f"{BEGINNER_COURSE_SLUG}-click-events-with-functions",
                    summary="Use functions and event listeners so the interface reacts to a user action.",
                    duration=28,
                    objectives=["Write a simple function for one task.", "Attach a click event listener.", "Describe what changes after the event fires."],
                    takeaways=["Functions keep repeated logic tidy.", "Event listeners make the page interactive."],
                    flow=["Write the function.", "Attach it to a click event.", "Test whether the UI updates as expected."],
                    markdown=(
                        "# Respond to click events with functions\n\n"
                        "This is where the interface stops being static. "
                        "An event listener watches for a user action, and a function decides what should happen next.\n\n"
                        "Keeping that behavior inside a named function makes the script easier to read and improve."
                    ),
                    practice="Add a button that changes text, color, or visibility when clicked.",
                    visual="## Visual aid\n`Click event` -> `Function runs` -> `Interface changes`",
                    playground=_web_playground(
                        "Make the button update its own label when clicked.",
                        "<button id=\"action-btn\">Try me</button>",
                        "button { padding: 12px 18px; border-radius: 999px; background: #2563eb; color: white; border: none; }",
                        "const button = document.getElementById('action-btn');\nfunction handleClick() {\n  if (button) {\n    button.textContent = 'Nice work';\n  }\n}\nbutton?.addEventListener('click', handleClick);\n",
                        [
                            {"label": "Use a function", "type": "includes", "target": "js", "value": "function"},
                            {"label": "Listen for click", "type": "includes", "target": "js", "value": "addEventListener"},
                            {"label": "Update the button text", "type": "includes", "target": "js", "value": "textContent"},
                        ],
                    ),
                ),
                _lesson(
                    title="Render small data collections into the page",
                    slug=f"{BEGINNER_COURSE_SLUG}-render-small-data-collections",
                    summary="Use arrays and objects to store simple records, then render them into repeated UI elements.",
                    duration=30,
                    objectives=["Shape small records with objects.", "Store several records in an array.", "Render the data into the DOM with a loop."],
                    takeaways=["Data shape affects rendering clarity.", "Rendering repeated UI from an array is a core frontend pattern."],
                    flow=["Model the data.", "Choose the render target.", "Loop through the records and display them."],
                    markdown=(
                        "# Render small data collections into the page\n\n"
                        "Many real interfaces display lists: projects, features, lessons, or users. "
                        "A useful beginner pattern is to keep the data in an array of objects and turn that data into visible markup.\n\n"
                        "This makes the interface easier to update later because the content is driven by data instead of hard-coded repeated HTML."
                    ),
                    practice="Create an array of three project objects and render them as cards inside a page section.",
                    visual="## Visual aid\n`Array of objects` -> `Loop` -> `Rendered cards`",
                ),
            ],
        },
    ],
    "milestone_projects": [
        {
            "title": "Build a beginner portfolio section",
            "description": "Combine semantic HTML, CSS, and responsive layout into one polished section you could place in a portfolio.",
            "milestoneOrder": 1,
            "estimatedHours": 3,
            "deliverables": ["Semantic section structure", "Styled UI block", "Responsive layout review"],
            "completionThreshold": 65,
        },
        {
            "title": "Create a small interactive project card list",
            "description": "Use JavaScript to update the DOM and render small project data into the page.",
            "milestoneOrder": 2,
            "estimatedHours": 4,
            "deliverables": ["One click interaction", "Rendered data cards", "Short explanation of the data flow"],
            "completionThreshold": 80,
        },
    ],
}


BEGINNER_QUIZ_BANK: dict[str, list[dict[str, Any]]] = {
    f"{BEGINNER_COURSE_SLUG}-html-foundations-quiz": [
        _question(
            "Why is semantic HTML useful in a beginner frontend project?",
            [
                "It replaces the need for CSS and JavaScript",
                "It makes the structure easier to understand, style, and maintain",
                "It automatically adds animations to the page",
                "It turns every page into a mobile app",
            ],
            "It makes the structure easier to understand, style, and maintain",
            "Semantic HTML gives the page a clearer structure, which makes styling and scripting easier later.",
            "Easy",
        ),
        _question(
            "Which tag is usually the best container for the primary content of a page?",
            ["<main>", "<title>", "<span>", "<meta>"],
            "<main>",
            "The main tag is intended to wrap the primary content of the page.",
            "Easy",
        ),
        _question(
            "What is the main purpose of a label in a form?",
            [
                "To decorate the form with more color",
                "To explain what information an input field expects",
                "To replace the submit button",
                "To force the form to use JavaScript",
            ],
            "To explain what information an input field expects",
            "Labels help learners and users understand what each input is for.",
            "Medium",
        ),
        _question(
            "Which content pattern creates the clearest hero section?",
            [
                "A heading, supporting text, and one clear call to action",
                "Five unrelated headings with no paragraph text",
                "Only an image with no explanation",
                "A footer placed above the main content",
            ],
            "A heading, supporting text, and one clear call to action",
            "A clear message, a little support text, and one action makes a hero easier to scan.",
            "Medium",
        ),
    ],
    f"{BEGINNER_COURSE_SLUG}-css-basics-quiz": [
        _question(
            "What does the CSS cascade describe?",
            [
                "How several CSS rules can apply to the same element and one rule wins",
                "How JavaScript loops through an array",
                "How a Git branch is merged",
                "How HTML headings are ordered",
            ],
            "How several CSS rules can apply to the same element and one rule wins",
            "The cascade explains how competing style rules are applied and which one takes effect.",
            "Easy",
        ),
        _question(
            "Which property creates space inside an element's border?",
            ["padding", "margin", "display", "color"],
            "padding",
            "Padding creates internal space between the content and the border.",
            "Easy",
        ),
        _question(
            "Why are reusable classes helpful when styling buttons and cards?",
            [
                "They guarantee the page will deploy automatically",
                "They keep repeated UI patterns consistent and reduce duplicated CSS",
                "They remove the need for HTML structure",
                "They force all buttons to look different",
            ],
            "They keep repeated UI patterns consistent and reduce duplicated CSS",
            "Reusable classes help repeated interface pieces stay visually consistent and easier to maintain.",
            "Medium",
        ),
        _question(
            "When should you use margin instead of padding?",
            [
                "When you want space between separate elements",
                "When you want text inside a button to move inward",
                "When you want to rename a class",
                "When you want to add JavaScript behavior",
            ],
            "When you want space between separate elements",
            "Margin creates external space between elements, while padding creates internal space.",
            "Medium",
        ),
    ],
    f"{BEGINNER_COURSE_SLUG}-responsive-layout-quiz": [
        _question(
            "Where do you usually apply `display: flex`?",
            [
                "On the parent container that controls the child layout",
                "On every text node in the page",
                "Only on the footer",
                "Only inside JavaScript",
            ],
            "On the parent container that controls the child layout",
            "Flexbox is applied to the parent so it can control the alignment and flow of its children.",
            "Easy",
        ),
        _question(
            "What does `flex-wrap` help with?",
            [
                "It allows items to move onto a new line when space gets tight",
                "It adds automatic API calls to the layout",
                "It deletes extra cards from the page",
                "It changes HTML into CSS",
            ],
            "It allows items to move onto a new line when space gets tight",
            "Wrap helps responsive rows avoid overflowing when the available width becomes smaller.",
            "Easy",
        ),
        _question(
            "Why is responsive review important after building a section?",
            [
                "Because a layout that works at one width may break at another",
                "Because it replaces the need for semantic HTML",
                "Because it makes the browser faster automatically",
                "Because it removes the need for spacing rules",
            ],
            "Because a layout that works at one width may break at another",
            "Responsive review checks whether the same section still reads clearly on smaller screens.",
            "Medium",
        ),
        _question(
            "Which outcome shows a row is adapting well on smaller screens?",
            [
                "Cards wrap or stack in a readable way instead of overflowing badly",
                "All content shrinks until it is unreadable",
                "The text disappears completely",
                "Every card is positioned with random margins",
            ],
            "Cards wrap or stack in a readable way instead of overflowing badly",
            "A good responsive layout keeps the content readable when space decreases.",
            "Medium",
        ),
    ],
    f"{BEGINNER_COURSE_SLUG}-javascript-basics-quiz": [
        _question(
            "Why do we store values in JavaScript variables?",
            [
                "To keep useful data available so the script can reuse it",
                "To replace all HTML tags",
                "To make CSS selectors stronger",
                "To publish the project to Vercel",
            ],
            "To keep useful data available so the script can reuse it",
            "Variables give the script a place to store information it needs again later.",
            "Easy",
        ),
        _question(
            "What does an event listener do?",
            [
                "It waits for a user action and then runs code in response",
                "It automatically writes semantic HTML",
                "It deletes unused CSS classes",
                "It turns an array into a database",
            ],
            "It waits for a user action and then runs code in response",
            "Event listeners connect user actions like clicks to JavaScript behavior.",
            "Easy",
        ),
        _question(
            "When rendering a list of project cards, which data shape is usually most useful?",
            ["An array of objects", "A single CSS declaration", "One heading element", "A browser tab title"],
            "An array of objects",
            "An array of objects is a practical way to store several similar records for rendering.",
            "Medium",
        ),
        _question(
            "What is DOM rendering in this beginner course?",
            [
                "Turning JavaScript data into visible content on the page",
                "Uploading code directly to GitHub",
                "Creating a CSS gradient background",
                "Renaming a file in VS Code",
            ],
            "Turning JavaScript data into visible content on the page",
            "DOM rendering is how JavaScript updates what the learner or user can see in the interface.",
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


def _curriculum_looks_like_scaffold(curriculum: dict[str, Any] | None) -> bool:
    if not curriculum:
        return True
    if curriculum.get("is_draft_scaffold"):
        return True
    modules = curriculum.get("modules", [])
    if not modules:
        return True
    return any(
        str(module.get("source") or "").strip().lower() == "scaffold"
        or str(module.get("title") or "").strip() == "Foundation Sprint"
        for module in modules
    )


def _curriculum_missing_lesson_games(curriculum: dict[str, Any] | None, expected_games: dict[str, str]) -> bool:
    if not curriculum:
        return True

    configured: dict[str, str] = {}
    for module in curriculum.get("modules", []):
        for lesson in module.get("lessons", []):
            lesson_slug = str(lesson.get("slug") or "").strip()
            game_key = str(lesson.get("gameKey") or "").strip()
            if lesson_slug and game_key:
                configured[lesson_slug] = game_key

    for lesson_slug, game_key in expected_games.items():
        if configured.get(lesson_slug) != game_key:
            return True
    return False


def _merge_lesson_game_keys(curriculum: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    template_game_keys: dict[str, str] = {}
    for module in template.get("modules", []):
        for lesson in module.get("lessons", []):
            lesson_slug = str(lesson.get("slug") or "").strip()
            game_key = str(lesson.get("gameKey") or "").strip()
            if lesson_slug and game_key:
                template_game_keys[lesson_slug] = game_key

    merged = deepcopy(curriculum)
    for module in merged.get("modules", []):
        for lesson in module.get("lessons", []):
            lesson_slug = str(lesson.get("slug") or "").strip()
            if lesson_slug in template_game_keys:
                lesson["gameKey"] = template_game_keys[lesson_slug]
    return merged


async def _replace_seed_questions(quiz_id: str, questions: list[dict[str, Any]], created_by: str) -> None:
    await quiz_questions_collection.delete_many({"quiz_id": quiz_id})
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
                "created_by": created_by,
                "created_at": created_at,
                "updated_at": created_at,
            }
            for question in questions
        ]
    )


async def ensure_frontend_development_beginner_seed() -> None:
    now = datetime.utcnow()
    summary = _curriculum_summary(BEGINNER_CURRICULUM_TEMPLATE)

    existing_course = await course_catalog_collection.find_one({"slug": BEGINNER_COURSE_SLUG})
    existing_curriculum = await course_curricula_collection.find_one({"course_slug": BEGINNER_COURSE_SLUG})
    should_upgrade_curriculum = _curriculum_looks_like_scaffold(existing_curriculum)

    if not existing_course:
        course_document = {
            "slug": BEGINNER_COURSE_SLUG,
            "title": BEGINNER_COURSE_TITLE,
            "description": (
                "Learn HTML, CSS, responsive layout, and beginner JavaScript by building clear page structure, "
                "styled components, responsive sections, and simple interactive UI pieces."
            ),
            "category": "Frontend Development",
            "difficulty": "Beginner",
            "duration": summary["duration"],
            "total_quizzes": summary["total_quizzes"],
            "total_lessons": summary["total_lessons"],
            "instructor": BEGINNER_SEED_AUTHOR,
            "prerequisites": [],
            "tags": ["html", "css", "flexbox", "responsive-design", "javascript", "dom"],
            "thumbnail": "",
            "thumbnail_public_id": "",
            "created_at": now,
            "updated_at": now,
        }
        result = await course_catalog_collection.insert_one(course_document)
        course_document["_id"] = result.inserted_id
        existing_course = course_document
        should_upgrade_curriculum = True
    elif should_upgrade_curriculum:
        await course_catalog_collection.update_one(
            {"slug": BEGINNER_COURSE_SLUG},
            {
                "$set": {
                    "title": BEGINNER_COURSE_TITLE,
                    "description": (
                        "Learn HTML, CSS, responsive layout, and beginner JavaScript by building clear page structure, "
                        "styled components, responsive sections, and simple interactive UI pieces."
                    ),
                    "category": "Frontend Development",
                    "difficulty": "Beginner",
                    "duration": summary["duration"],
                    "total_quizzes": summary["total_quizzes"],
                    "total_lessons": summary["total_lessons"],
                    "instructor": BEGINNER_SEED_AUTHOR,
                    "prerequisites": [],
                    "tags": ["html", "css", "flexbox", "responsive-design", "javascript", "dom"],
                    "updated_at": now,
                }
            },
        )
        existing_course = await course_catalog_collection.find_one({"slug": BEGINNER_COURSE_SLUG})

    if should_upgrade_curriculum:
        curriculum_document = deepcopy(BEGINNER_CURRICULUM_TEMPLATE)
        curriculum_document.update(
            {
                "course_slug": BEGINNER_COURSE_SLUG,
                "updated_at": now,
                "updated_by": BEGINNER_SEED_AUTHOR,
                "is_draft_scaffold": False,
            }
        )
        await course_curricula_collection.update_one(
            {"course_slug": BEGINNER_COURSE_SLUG},
            {"$set": curriculum_document},
            upsert=True,
        )
        existing_curriculum = await course_curricula_collection.find_one({"course_slug": BEGINNER_COURSE_SLUG})

    if existing_course and existing_curriculum:
        await LessonLibraryService.sync_course_lessons(existing_course, existing_curriculum, BEGINNER_SEED_AUTHOR)

    if not should_upgrade_curriculum:
        return

    for quiz_id, questions in BEGINNER_QUIZ_BANK.items():
        await _replace_seed_questions(quiz_id, questions, BEGINNER_SEED_AUTHOR)


async def ensure_frontend_development_foundations_seed() -> None:
    now = datetime.utcnow()
    summary = _curriculum_summary(FOUNDATIONS_CURRICULUM_TEMPLATE)

    existing_course = await course_catalog_collection.find_one({"slug": FOUNDATIONS_COURSE_SLUG})
    existing_curriculum = await course_curricula_collection.find_one({"course_slug": FOUNDATIONS_COURSE_SLUG})
    expected_games = {
        f"{FOUNDATIONS_COURSE_SLUG}-semantic-structure-audit": "semantic-sleuth",
        f"{FOUNDATIONS_COURSE_SLUG}-css-grid-two-dimensional-layouts": "grid-studio",
        f"{FOUNDATIONS_COURSE_SLUG}-hover-focus-success-error-states": "ui-mood-runway",
        f"{FOUNDATIONS_COURSE_SLUG}-array-methods-transform-interface-data": "data-remix-club",
        f"{FOUNDATIONS_COURSE_SLUG}-fetch-data-with-ui-states": "signal-rescue-mission",
    }
    scaffold_upgrade_needed = _curriculum_looks_like_scaffold(existing_curriculum)
    game_metadata_refresh_needed = _curriculum_missing_lesson_games(existing_curriculum, expected_games)
    should_upgrade_curriculum = scaffold_upgrade_needed or game_metadata_refresh_needed

    if not existing_course:
        course_document = {
            "slug": FOUNDATIONS_COURSE_SLUG,
            "title": FOUNDATIONS_COURSE_TITLE,
            "description": (
                "Deepen HTML, CSS, and JavaScript fundamentals through stronger structure, layout systems, "
                "accessible forms, dynamic DOM patterns, and small data-driven frontend features."
            ),
            "category": "Frontend Development",
            "difficulty": "Beginner",
            "duration": summary["duration"],
            "total_quizzes": summary["total_quizzes"],
            "total_lessons": summary["total_lessons"],
            "instructor": FOUNDATIONS_SEED_AUTHOR,
            "prerequisites": ["frontend-development-beginner"],
            "tags": ["html", "css", "grid", "flexbox", "forms", "javascript", "dom", "async"],
            "thumbnail": "",
            "thumbnail_public_id": "",
            "created_at": now,
            "updated_at": now,
        }
        result = await course_catalog_collection.insert_one(course_document)
        course_document["_id"] = result.inserted_id
        existing_course = course_document
        scaffold_upgrade_needed = True
        should_upgrade_curriculum = True
    elif scaffold_upgrade_needed:
        await course_catalog_collection.update_one(
            {"slug": FOUNDATIONS_COURSE_SLUG},
            {
                "$set": {
                    "title": FOUNDATIONS_COURSE_TITLE,
                    "description": (
                        "Deepen HTML, CSS, and JavaScript fundamentals through stronger structure, layout systems, "
                        "accessible forms, dynamic DOM patterns, and small data-driven frontend features."
                    ),
                    "category": "Frontend Development",
                    "difficulty": "Beginner",
                    "duration": summary["duration"],
                    "total_quizzes": summary["total_quizzes"],
                    "total_lessons": summary["total_lessons"],
                    "instructor": FOUNDATIONS_SEED_AUTHOR,
                    "prerequisites": ["frontend-development-beginner"],
                    "tags": ["html", "css", "grid", "flexbox", "forms", "javascript", "dom", "async"],
                    "updated_at": now,
                }
            },
        )
        existing_course = await course_catalog_collection.find_one({"slug": FOUNDATIONS_COURSE_SLUG})

    if should_upgrade_curriculum:
        if scaffold_upgrade_needed:
            curriculum_document = deepcopy(FOUNDATIONS_CURRICULUM_TEMPLATE)
            curriculum_document.update(
                {
                    "course_slug": FOUNDATIONS_COURSE_SLUG,
                    "updated_at": now,
                    "updated_by": FOUNDATIONS_SEED_AUTHOR,
                    "is_draft_scaffold": False,
                }
            )
        else:
            curriculum_document = _merge_lesson_game_keys(existing_curriculum or {}, FOUNDATIONS_CURRICULUM_TEMPLATE)
            curriculum_document.update(
                {
                    "course_slug": FOUNDATIONS_COURSE_SLUG,
                    "updated_at": now,
                    "updated_by": FOUNDATIONS_SEED_AUTHOR,
                }
            )
        await course_curricula_collection.update_one(
            {"course_slug": FOUNDATIONS_COURSE_SLUG},
            {"$set": curriculum_document},
            upsert=True,
        )
        existing_curriculum = await course_curricula_collection.find_one({"course_slug": FOUNDATIONS_COURSE_SLUG})

    if existing_course and existing_curriculum:
        await LessonLibraryService.sync_course_lessons(existing_course, existing_curriculum, FOUNDATIONS_SEED_AUTHOR)

    if not scaffold_upgrade_needed:
        return

    for quiz_id, questions in FOUNDATIONS_QUIZ_BANK.items():
        await _replace_seed_questions(quiz_id, questions, FOUNDATIONS_SEED_AUTHOR)


FOUNDATIONS_COURSE_SLUG = "frontend-development-foundations"
FOUNDATIONS_COURSE_TITLE = "Frontend Development Foundations"
FOUNDATIONS_SEED_AUTHOR = "Deveda Frontend Team"

FOUNDATIONS_CURRICULUM_TEMPLATE: dict[str, Any] = {
    "overview": (
        "Frontend Development Foundations deepens HTML, CSS, and JavaScript through more intentional interface work. "
        "Learners move from solid page structure into accessibility, layout systems, form experience, rendering patterns, "
        "and small data-driven features that feel closer to real frontend projects."
    ),
    "learning_flow": [
        "Refine structure and content quality so interfaces are clearer and more accessible.",
        "Use stronger CSS layout systems and design rules instead of one-off styling decisions.",
        "Build forms and interactive UI states that guide the user well.",
        "Use JavaScript patterns to render, update, and organize interface behavior more confidently.",
        "Finish with async data and a mini project structure that combines the course skills.",
    ],
    "visual_aid_markdown": (
        "## Course roadmap\n"
        "`Structure and accessibility` -> `Layout systems` -> `Form experience` -> `DOM patterns` -> `Async features`\n\n"
        "The foundations stage should feel more deliberate than beginner work: cleaner architecture, clearer states, and better user guidance."
    ),
    "modules": [
        {
            "title": "Structure, Semantics, and Accessibility",
            "description": "Improve page structure so content is easier to scan, navigate, and explain.",
            "order": 1,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Structure and accessibility quiz",
            "assessmentQuizId": f"{FOUNDATIONS_COURSE_SLUG}-structure-accessibility-quiz",
            "lessons": [
                _lesson(
                    title="Audit and improve semantic page structure",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-semantic-structure-audit",
                    summary="Review an existing page and improve the meaning of its sections before touching style.",
                    duration=24,
                    objectives=["Spot vague or overused containers.", "Replace generic structure with semantic sections where appropriate.", "Explain why the revised structure is easier to maintain."],
                    takeaways=["Structure should describe purpose before presentation.", "Auditing markup is a practical frontend skill, not just a theory exercise."],
                    flow=["Read the page outline.", "Spot unclear structure.", "Replace generic wrappers with meaningful sections.", "Review whether the document reads more clearly."],
                    markdown=(
                        "# Audit and improve semantic page structure\n\n"
                        "Foundations-level frontend work includes reviewing what already exists and making it clearer. "
                        "A page full of anonymous wrappers can still look correct, but it is harder to understand, style, and maintain.\n\n"
                        "The goal in this lesson is to read a page like a teammate would: what is the header, what is the main flow, "
                        "which parts are related, and what belongs in supporting areas rather than the primary content?"
                    ),
                    practice="Take one small page you already built and rewrite at least three generic wrappers into clearer semantic sections.",
                    visual="## Visual aid\n`Current structure` -> `Audit` -> `Clearer document outline`",
                    game_key="semantic-sleuth",
                ),
                _lesson(
                    title="Use lists, grouped content, and supporting copy intentionally",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-lists-grouped-content-supporting-copy",
                    summary="Choose the right content patterns so repeated information and supporting text feel organized.",
                    duration=22,
                    objectives=["Recognize when content should become a list or grouped section.", "Write supporting copy that improves scanning.", "Avoid flat walls of unrelated content."],
                    takeaways=["Good structure improves comprehension before styling does.", "Repeated content becomes easier to work with when it follows one visible pattern."],
                    flow=["Identify repeated content.", "Choose a grouping pattern.", "Rewrite headings and support text to match the content purpose."],
                    markdown=(
                        "# Use lists, grouped content, and supporting copy intentionally\n\n"
                        "As interfaces grow, plain paragraphs are not always enough. "
                        "Features, benefits, navigation items, and process steps often need list or card patterns so the structure matches the content.\n\n"
                        "This lesson focuses on choosing the right content container and keeping the written copy aligned with it."
                    ),
                    practice="Turn a plain block of repeated feature text into a clearer grouped section with headings and short support text.",
                    visual="## Visual aid\n`Repeated information` -> `Grouped pattern` -> `Easier scanning`",
                ),
                _lesson(
                    title="Write more accessible links, images, and labels",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-accessible-links-images-labels",
                    summary="Improve interface clarity by making links, images, and labels more descriptive and intentional.",
                    duration=24,
                    objectives=["Replace vague link text with clearer actions.", "Add image descriptions that support the page meaning.", "Use labels and helper text that reduce guesswork."],
                    takeaways=["Accessibility often starts with clearer wording.", "Descriptive content choices help everyone, not only assistive technology users."],
                    flow=["Inspect current wording.", "Rewrite vague text.", "Check whether the meaning stays clear without visual cues."],
                    markdown=(
                        "# Write more accessible links, images, and labels\n\n"
                        "Accessibility is not only a checklist of attributes. "
                        "It often begins with language: clear links, clear form labels, and image descriptions that support understanding.\n\n"
                        "A foundations-level frontend developer should notice when interface wording is too vague and know how to rewrite it."
                    ),
                    practice="Replace at least three vague pieces of interface text with clearer links, labels, or image descriptions.",
                    visual="## Visual aid\n`Vague wording` -> `Clear intent` -> `More usable interface`",
                ),
            ],
        },
        {
            "title": "CSS Layout Systems and Design Consistency",
            "description": "Use stronger layout systems and repeatable design rules instead of one-off styling fixes.",
            "order": 2,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Layout systems quiz",
            "assessmentQuizId": f"{FOUNDATIONS_COURSE_SLUG}-layout-systems-quiz",
            "lessons": [
                _lesson(
                    title="Use CSS Grid for two-dimensional layouts",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-css-grid-two-dimensional-layouts",
                    summary="Use Grid when rows and columns both matter in the interface.",
                    duration=28,
                    objectives=["Explain when Grid is more useful than Flexbox.", "Create a simple row-and-column layout.", "Use gaps and template rules intentionally."],
                    takeaways=["Grid is useful when both axes matter.", "Choosing the right layout tool leads to cleaner CSS."],
                    flow=["Identify the layout problem.", "Choose rows and columns.", "Apply grid rules and inspect the result."],
                    markdown=(
                        "# Use CSS Grid for two-dimensional layouts\n\n"
                        "Flexbox is excellent for one-direction flows, but some interfaces care about both rows and columns at the same time. "
                        "That is where Grid becomes especially useful.\n\n"
                        "This lesson is about recognizing the difference and using Grid when it gives the layout more structure with less friction."
                    ),
                    practice="Build a simple dashboard or feature area using Grid with clear row and column spacing.",
                    visual="## Visual aid\n`Two-dimensional layout` -> `Grid tracks` -> `Structured interface`",
                    game_key="grid-studio",
                    playground=_web_playground(
                        "Create a simple two-column grid section.",
                        "<section class=\"dashboard-grid\">\n  <article class=\"panel\">Overview</article>\n  <article class=\"panel\">Progress</article>\n  <article class=\"panel\">Tasks</article>\n  <article class=\"panel\">Notes</article>\n</section>",
                        ".panel { padding: 1rem; background: white; border-radius: 1rem; }\n",
                        "",
                        [
                            {"label": "Use display grid", "type": "includes", "target": "css", "value": "display: grid"},
                            {"label": "Define columns", "type": "includes", "target": "css", "value": "grid-template-columns"},
                            {"label": "Add gap spacing", "type": "includes", "target": "css", "value": "gap"},
                        ],
                    ),
                ),
                _lesson(
                    title="Combine Grid, Flexbox, and reusable spacing rules",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-combine-grid-flexbox-and-spacing-rules",
                    summary="Mix layout tools intentionally so each layer of the interface uses the simplest rule that fits.",
                    duration=26,
                    objectives=["Choose the right layout tool for a section.", "Avoid overcomplicating child alignment rules.", "Use spacing consistently across nested components."],
                    takeaways=["Good CSS often combines tools instead of forcing one tool everywhere.", "Spacing consistency helps the whole interface feel more deliberate."],
                    flow=["Choose the outer layout.", "Choose the inner alignment pattern.", "Apply consistent gaps and spacing decisions."],
                    markdown=(
                        "# Combine Grid, Flexbox, and reusable spacing rules\n\n"
                        "A stronger frontend layout rarely uses only one pattern everywhere. "
                        "An outer section may need Grid, while the inside of a card may need Flexbox. "
                        "What matters is that each layer uses the simplest rule for its job.\n\n"
                        "This lesson teaches layout composition rather than isolated properties."
                    ),
                    practice="Build one section where the outer area uses Grid and the inside of at least one card uses Flexbox.",
                    visual="## Visual aid\n`Outer structure` -> `Inner alignment` -> `Consistent spacing`",
                ),
                _lesson(
                    title="Create a clearer visual system with color, typography, and hierarchy",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-visual-system-with-color-typography-and-hierarchy",
                    summary="Use a small visual system so headings, body text, actions, and emphasis feel related.",
                    duration=24,
                    objectives=["Create a simple text hierarchy.", "Use color with a clear purpose.", "Keep repeated visual roles consistent across the page."],
                    takeaways=["Visual consistency is part of frontend engineering, not only design polish.", "Small systems are easier to maintain than isolated style choices."],
                    flow=["Define a few repeated visual roles.", "Apply them consistently.", "Check whether hierarchy remains clear across sections."],
                    markdown=(
                        "# Create a clearer visual system with color, typography, and hierarchy\n\n"
                        "Foundations-level work should feel more intentional than a collection of random styles. "
                        "A small visual system makes the interface easier to scan and easier to extend.\n\n"
                        "Think in roles: heading text, support text, emphasis, primary action, secondary action. "
                        "Once those roles are clear, styling decisions become more consistent."
                    ),
                    practice="Choose one heading style, one body style, one accent color, and one primary action style, then apply them across a page section.",
                    visual="## Visual aid\n`Visual roles` -> `Consistent rules` -> `Clearer hierarchy`",
                ),
            ],
        },
        {
            "title": "Forms, States, and User Feedback",
            "description": "Create forms and interface states that guide the user clearly through action and feedback.",
            "order": 3,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Forms and feedback quiz",
            "assessmentQuizId": f"{FOUNDATIONS_COURSE_SLUG}-forms-feedback-quiz",
            "lessons": [
                _lesson(
                    title="Build more usable forms with grouped fields and helper text",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-usable-forms-grouped-fields-helper-text",
                    summary="Organize forms so inputs, labels, and helper text work together to reduce confusion.",
                    duration=24,
                    objectives=["Group related fields into meaningful sections.", "Use helper text to set expectations.", "Keep form flow easy to scan."],
                    takeaways=["Good forms reduce guessing.", "Grouped form structure improves both readability and maintenance."],
                    flow=["Map the input journey.", "Group related fields.", "Add helper text only where it truly helps."],
                    markdown=(
                        "# Build more usable forms with grouped fields and helper text\n\n"
                        "A foundations-level form should guide the learner or user instead of forcing them to interpret each field alone. "
                        "Grouping, headings, and light helper text create a stronger experience than a long stack of disconnected inputs."
                    ),
                    practice="Refactor a basic form into grouped field sections with clearer labels and short helper text where needed.",
                    visual="## Visual aid\n`Field groups` -> `Helper text` -> `Lower confusion`",
                ),
                _lesson(
                    title="Style hover, focus, success, and error states",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-hover-focus-success-error-states",
                    summary="Make interactive elements easier to understand by styling their important states clearly.",
                    duration=26,
                    objectives=["Differentiate between interaction states.", "Use visual feedback to support understanding.", "Keep state styles readable and consistent."],
                    takeaways=["States are part of the interface, not an optional polish layer.", "Focus and error styles should be visible enough to guide action."],
                    flow=["List the key states.", "Style each state intentionally.", "Test whether the change communicates useful feedback."],
                    markdown=(
                        "# Style hover, focus, success, and error states\n\n"
                        "Users should be able to tell when an element is clickable, selected, focused, or invalid. "
                        "That means interface states need to be designed and implemented, not left to accident.\n\n"
                        "This lesson strengthens the connection between CSS styling and actual user guidance."
                    ),
                    practice="Style a form input and button so hover, focus, and at least one validation state are clearly visible.",
                    visual="## Visual aid\n`Interaction state` -> `Visual feedback` -> `User guidance`",
                    game_key="ui-mood-runway",
                ),
                _lesson(
                    title="Validate and communicate user input with JavaScript",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-validate-and-communicate-user-input",
                    summary="Use small validation rules and messages so forms respond clearly to what the user enters.",
                    duration=28,
                    objectives=["Check simple form conditions with JavaScript.", "Display useful feedback messages.", "Avoid vague success and error wording."],
                    takeaways=["Validation should guide, not punish.", "JavaScript can improve the form experience when it is tied to clear messaging."],
                    flow=["Choose the condition to check.", "Run the validation on action.", "Show feedback that tells the user what to do next."],
                    markdown=(
                        "# Validate and communicate user input with JavaScript\n\n"
                        "Validation is more than blocking a submission. "
                        "It is an opportunity to guide the user back toward success with clear, timely feedback.\n\n"
                        "In foundations work, simple checks and useful messages are more important than complicated rule systems."
                    ),
                    practice="Add a small form validation rule and show a helpful success or error message based on the result.",
                    visual="## Visual aid\n`Input` -> `Check rule` -> `Helpful feedback`",
                ),
            ],
        },
        {
            "title": "JavaScript Patterns for Dynamic Interfaces",
            "description": "Use stronger JavaScript patterns to render data, manage UI state, and keep DOM updates organized.",
            "order": 4,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Dynamic interfaces quiz",
            "assessmentQuizId": f"{FOUNDATIONS_COURSE_SLUG}-dynamic-interfaces-quiz",
            "lessons": [
                _lesson(
                    title="Use array methods to transform interface data",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-array-methods-transform-interface-data",
                    summary="Use methods like map and filter to shape the data before rendering it.",
                    duration=26,
                    objectives=["Use array methods to transform repeated data.", "Choose data preparation steps before rendering.", "Explain why transformed data is easier to display."],
                    takeaways=["Preparing data first makes rendering cleaner.", "Array methods are core frontend tools for list-based interfaces."],
                    flow=["Start with raw data.", "Transform or filter it.", "Render the prepared result."],
                    markdown=(
                        "# Use array methods to transform interface data\n\n"
                        "Rendering becomes easier when the data already looks like the UI you want to display. "
                        "Instead of mixing all logic inside a render step, use array methods first to shape the data.\n\n"
                        "This creates cleaner code and a clearer mental model."
                    ),
                    practice="Take a small dataset and use an array method to filter or reshape it before showing it in the DOM.",
                    visual="## Visual aid\n`Raw data` -> `Transform` -> `Cleaner render`",
                    game_key="data-remix-club",
                ),
                _lesson(
                    title="Build reusable render functions for repeated UI blocks",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-reusable-render-functions",
                    summary="Wrap repeated DOM rendering logic inside named functions so the UI is easier to update.",
                    duration=28,
                    objectives=["Extract repeated rendering logic into a function.", "Pass data into that function clearly.", "Reduce duplicated DOM output code."],
                    takeaways=["Named render functions make UI code easier to follow.", "Reusability matters in interface logic as much as it does in styles."],
                    flow=["Spot repeated output logic.", "Move it into a function.", "Call the function with different records or states."],
                    markdown=(
                        "# Build reusable render functions for repeated UI blocks\n\n"
                        "A longer script becomes easier to manage when rendering logic has names and boundaries. "
                        "Instead of scattering template strings and DOM updates everywhere, create functions that describe what they produce."
                    ),
                    practice="Create one render function that returns or injects a repeated card pattern for multiple records.",
                    visual="## Visual aid\n`Repeated output` -> `Render function` -> `Reusable UI logic`",
                ),
                _lesson(
                    title="Manage UI state with classes, flags, and event-driven updates",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-manage-ui-state-with-events",
                    summary="Track whether parts of the interface are open, active, filtered, or loading, then update the DOM accordingly.",
                    duration=30,
                    objectives=["Represent a small piece of UI state in code.", "Update the DOM when that state changes.", "Use classes or text changes to reflect the current state."],
                    takeaways=["State is simply the current condition of the interface.", "Event-driven updates become easier when the current state is explicit."],
                    flow=["Define the current state.", "Change it through an event.", "Reflect that change in the visible interface."],
                    markdown=(
                        "# Manage UI state with classes, flags, and event-driven updates\n\n"
                        "Interfaces often need to know whether something is expanded, selected, loading, visible, or filtered. "
                        "That current condition is UI state.\n\n"
                        "Foundations-level work means making state explicit enough that the DOM can reliably follow it."
                    ),
                    practice="Build a small filter, accordion, or tab interaction that updates the UI when the state changes.",
                    visual="## Visual aid\n`Current state` -> `Event changes state` -> `DOM reflects change`",
                ),
            ],
        },
        {
            "title": "Async Data and Mini Project Architecture",
            "description": "Combine frontend structure, styling, and dynamic behavior into a small project that handles live data clearly.",
            "order": 5,
            "source": "seed",
            "generationStatus": "generated",
            "assessmentTitle": "Async data and project quiz",
            "assessmentQuizId": f"{FOUNDATIONS_COURSE_SLUG}-async-project-quiz",
            "lessons": [
                _lesson(
                    title="Fetch data and show loading, success, and error states",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-fetch-data-with-ui-states",
                    summary="Use async and await with interface states so live data feels understandable to the user.",
                    duration=32,
                    objectives=["Fetch data with async and await.", "Represent loading and error states in the UI.", "Show useful content once the request succeeds."],
                    takeaways=["Async features need interface feedback, not only console output.", "Loading and error states are part of a complete frontend experience."],
                    flow=["Start the request.", "Show loading state.", "Handle success or failure.", "Update the interface with the right state."],
                    markdown=(
                        "# Fetch data and show loading, success, and error states\n\n"
                        "A frontend feature is not finished when the fetch call works in the console. "
                        "The interface should also communicate what is happening: loading, success, or failure.\n\n"
                        "This lesson connects async JavaScript to visible user experience."
                    ),
                    practice="Fetch a small dataset and show one loading message, one success state, and one error fallback.",
                    visual="## Visual aid\n`Request starts` -> `Loading UI` -> `Success or error`",
                    game_key="signal-rescue-mission",
                    playground=_js_playground(
                        "Write an async function that fetches data and logs the first item.",
                        "async function loadData() {\n  const response = await fetch('https://jsonplaceholder.typicode.com/posts');\n  const data = await response.json();\n  console.log(data[0].title);\n}\n\nloadData();\n",
                        [
                            {"label": "Use async function syntax", "type": "includes", "target": "js", "value": "async function"},
                            {"label": "Await a fetch call", "type": "includes", "target": "js", "value": "await fetch"},
                            {"label": "Parse JSON", "type": "includes", "target": "js", "value": "response.json"},
                        ],
                    ),
                ),
                _lesson(
                    title="Structure a mini frontend project for maintainability",
                    slug=f"{FOUNDATIONS_COURSE_SLUG}-mini-project-structure-for-maintainability",
                    summary="Organize files, sections, and render logic so a small project is easier to explain and improve.",
                    duration=30,
                    objectives=["Break a small project into clear responsibilities.", "Keep HTML, CSS, and JavaScript roles understandable.", "Prepare the project for review or extension."],
                    takeaways=["Project structure affects maintainability, not only aesthetics.", "Clear file and feature boundaries make future iteration easier."],
                    flow=["List the project parts.", "Assign responsibilities by file or section.", "Review whether the build would make sense to another developer."],
                    markdown=(
                        "# Structure a mini frontend project for maintainability\n\n"
                        "Foundations-level work should not feel like one long file with every decision mixed together. "
                        "Even a small project benefits from clear boundaries between structure, style, and behavior.\n\n"
                        "This lesson turns several earlier skills into a project organization habit that scales better."
                    ),
                    practice="Outline a mini project with one clear page goal, organized files, one dynamic feature, and one short explanation of how the parts fit together.",
                    visual="## Visual aid\n`Project goal` -> `Clear sections` -> `Organized files` -> `Easier iteration`",
                    content_type="project",
                ),
            ],
        },
    ],
    "milestone_projects": [
        {
            "title": "Accessibility and layout refinement review",
            "description": "Refactor a small interface so its structure, hierarchy, and layout are more deliberate than a beginner first draft.",
            "milestoneOrder": 1,
            "estimatedHours": 4,
            "deliverables": ["Improved semantic structure", "Clearer grouped content", "Stronger responsive layout decisions"],
            "completionThreshold": 70,
        },
        {
            "title": "Dynamic UI mini project",
            "description": "Build a small data-driven frontend feature with visible states and clearer project organization.",
            "milestoneOrder": 2,
            "estimatedHours": 5,
            "deliverables": ["Rendered data from JavaScript", "Interactive or validated UI state", "Short explanation of structure and logic"],
            "completionThreshold": 82,
        },
    ],
}


FOUNDATIONS_QUIZ_BANK: dict[str, list[dict[str, Any]]] = {
    f"{FOUNDATIONS_COURSE_SLUG}-structure-accessibility-quiz": [
        _question(
            "Why should a developer audit page structure before focusing on styles?",
            [
                "Because clearer structure makes the interface easier to understand and maintain",
                "Because CSS only works on perfectly audited pages",
                "Because semantic tags automatically create animations",
                "Because layout systems are not allowed until the audit is complete",
            ],
            "Because clearer structure makes the interface easier to understand and maintain",
            "A clear document structure helps both maintenance and later styling decisions.",
            "Easy",
        ),
        _question(
            "When repeated content items follow the same pattern, what usually helps most?",
            [
                "Grouping them in a list or shared section pattern",
                "Changing every item to a different structure",
                "Removing all headings",
                "Placing all items inside the footer",
            ],
            "Grouping them in a list or shared section pattern",
            "Repeated content is easier to scan and style when it uses one clear structural pattern.",
            "Easy",
        ),
        _question(
            "What improves link accessibility the most in many beginner interfaces?",
            [
                "Writing clearer link text that explains the destination or action",
                "Making every link open in a new tab",
                "Using only uppercase letters",
                "Removing supporting text around the link",
            ],
            "Writing clearer link text that explains the destination or action",
            "Descriptive link text improves clarity and usability for many kinds of users.",
            "Medium",
        ),
        _question(
            "Why are better labels useful in forms?",
            [
                "They help the user understand what each input expects",
                "They eliminate the need for submit buttons",
                "They automatically validate the form",
                "They replace JavaScript",
            ],
            "They help the user understand what each input expects",
            "Labels reduce ambiguity by telling the user what the field is for.",
            "Medium",
        ),
    ],
    f"{FOUNDATIONS_COURSE_SLUG}-layout-systems-quiz": [
        _question(
            "When is CSS Grid often a better choice than Flexbox?",
            [
                "When the layout depends on both rows and columns",
                "When only one button needs centering",
                "When writing a fetch request",
                "When creating a Git commit",
            ],
            "When the layout depends on both rows and columns",
            "Grid is especially useful for two-dimensional layouts where rows and columns both matter.",
            "Easy",
        ),
        _question(
            "Why might one section use Grid while a card inside it uses Flexbox?",
            [
                "Because different layout layers can have different needs",
                "Because Grid and Flexbox cannot appear in the same project",
                "Because Flexbox only works inside forms",
                "Because Grid automatically writes HTML",
            ],
            "Because different layout layers can have different needs",
            "Using the simplest tool for each layer often produces cleaner layout code.",
            "Medium",
        ),
        _question(
            "What does a small visual system improve?",
            [
                "Consistency in hierarchy, actions, and repeated interface roles",
                "Only the file size of the CSS",
                "The speed of GitHub pushes",
                "Automatic backend validation",
            ],
            "Consistency in hierarchy, actions, and repeated interface roles",
            "A visual system helps headings, actions, and supporting text feel related across the interface.",
            "Medium",
        ),
        _question(
            "Which choice best supports layout consistency?",
            [
                "Using repeatable spacing and style rules across similar components",
                "Styling every section with unrelated values",
                "Avoiding all reusable classes",
                "Changing colors on every card for variety",
            ],
            "Using repeatable spacing and style rules across similar components",
            "Consistent spacing and repeated style rules make interfaces easier to scan and maintain.",
            "Medium",
        ),
    ],
    f"{FOUNDATIONS_COURSE_SLUG}-forms-feedback-quiz": [
        _question(
            "Why should related form fields be grouped together?",
            [
                "It helps the user understand the flow of the form more easily",
                "It removes the need for labels",
                "It guarantees the form will submit successfully",
                "It turns the form into a database",
            ],
            "It helps the user understand the flow of the form more easily",
            "Grouping makes longer or more detailed forms easier to scan and complete.",
            "Easy",
        ),
        _question(
            "What is the main purpose of focus styling?",
            [
                "To show clearly which interactive element is currently active",
                "To hide form errors",
                "To replace hover states entirely",
                "To style only mouse users",
            ],
            "To show clearly which interactive element is currently active",
            "Focus styles help users understand where they are in the interaction flow.",
            "Medium",
        ),
        _question(
            "What makes validation feedback more useful?",
            [
                "It explains what went wrong and what the user should do next",
                "It only says error without any detail",
                "It appears only in the browser console",
                "It disables the form permanently",
            ],
            "It explains what went wrong and what the user should do next",
            "Helpful validation messages guide the user toward a successful correction.",
            "Medium",
        ),
        _question(
            "Why are success and error states part of frontend work?",
            [
                "Because the interface should communicate what is happening to the user",
                "Because they replace semantic HTML",
                "Because they only matter to backend systems",
                "Because they are decorative only",
            ],
            "Because the interface should communicate what is happening to the user",
            "State styling and messaging are part of the user experience, not just decoration.",
            "Medium",
        ),
    ],
    f"{FOUNDATIONS_COURSE_SLUG}-dynamic-interfaces-quiz": [
        _question(
            "Why use array methods before rendering data?",
            [
                "They help shape the data into a cleaner form for the interface",
                "They replace the DOM completely",
                "They remove the need for variables",
                "They force all arrays to become objects",
            ],
            "They help shape the data into a cleaner form for the interface",
            "Preparing data before rendering often makes the DOM update logic simpler and clearer.",
            "Easy",
        ),
        _question(
            "What is the main benefit of a reusable render function?",
            [
                "It keeps repeated UI output logic easier to read and reuse",
                "It guarantees a faster internet connection",
                "It removes the need for CSS classes",
                "It replaces event listeners",
            ],
            "It keeps repeated UI output logic easier to read and reuse",
            "Render functions give repeated UI generation a clear boundary and name.",
            "Medium",
        ),
        _question(
            "What does UI state describe?",
            [
                "The current condition of the interface, such as open, loading, or selected",
                "The number of CSS files in the project",
                "The repository branch name",
                "The course category stored in the database",
            ],
            "The current condition of the interface, such as open, loading, or selected",
            "UI state tracks what condition the interface is in so the DOM can reflect it correctly.",
            "Medium",
        ),
        _question(
            "Why should the DOM reflect state changes clearly?",
            [
                "So the visible interface stays aligned with what the code thinks is happening",
                "So the console output stays shorter",
                "So semantic HTML is no longer needed",
                "So event listeners can be removed",
            ],
            "So the visible interface stays aligned with what the code thinks is happening",
            "Clear DOM updates keep the interface behavior understandable and trustworthy.",
            "Medium",
        ),
    ],
    f"{FOUNDATIONS_COURSE_SLUG}-async-project-quiz": [
        _question(
            "Why is a loading state useful during a fetch request?",
            [
                "It tells the user that data is being requested and the interface is still working",
                "It replaces the API response",
                "It guarantees the request will succeed",
                "It deletes previous results from the database",
            ],
            "It tells the user that data is being requested and the interface is still working",
            "Loading states help users understand that the interface has not frozen while waiting for data.",
            "Easy",
        ),
        _question(
            "What should happen if a fetch request fails in the UI?",
            [
                "The interface should show a clear error state or fallback message",
                "The page should silently do nothing",
                "Every button should be hidden permanently",
                "The CSS file should be removed",
            ],
            "The interface should show a clear error state or fallback message",
            "A visible error or fallback state helps the user understand what happened and what to do next.",
            "Medium",
        ),
        _question(
            "Why does small project structure matter even in a foundations course?",
            [
                "Because clearer file and feature boundaries make projects easier to explain and improve",
                "Because small projects never change after the first draft",
                "Because structure only matters in backend systems",
                "Because organization is purely aesthetic",
            ],
            "Because clearer file and feature boundaries make projects easier to explain and improve",
            "Project structure affects maintainability, collaboration, and future changes.",
            "Medium",
        ),
        _question(
            "Which project result best matches this module?",
            [
                "A mini frontend feature with live data, visible states, and organized code",
                "A plain page with no dynamic behavior",
                "A single screenshot of an unfinished mockup",
                "A backend-only service with no interface",
            ],
            "A mini frontend feature with live data, visible states, and organized code",
            "This module is about combining async data, UI states, and project organization into one practical frontend result.",
            "Medium",
        ),
    ],
}
