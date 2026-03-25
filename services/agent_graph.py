from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


class AgentChatState(TypedDict, total=False):
    assignment: dict
    thread: dict
    current_user: dict
    payload: Any
    history: list[dict]
    context: dict
    tools_used: list[str]
    artifacts: list[dict]
    controlled_reply: Optional[dict]
    ai_reply: Optional[dict]
    steps: list[str]


class AgentActionState(TypedDict, total=False):
    assignment: dict
    payload: Any
    current_user: dict
    context: dict
    artifact: Optional[dict]
    steps: list[str]


def _agent_services():
    from services import agent_services

    return agent_services


def _append_step(state: dict, step: str) -> list[str]:
    return [*state.get("steps", []), step]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
            elif item:
                parts.append(str(item).strip())
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def _to_langchain_messages(messages: list[dict]) -> list[Any]:
    converted: list[Any] = []
    for message in messages:
        role = str(message.get("role", "user")).strip().lower()
        content = _content_to_text(message.get("content"))
        if not content:
            continue
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def _build_chat_model(*, timeout: int, temperature: float, json_mode: bool = False) -> Optional[ChatOpenAI]:
    if not OPENAI_API_KEY:
        return None

    model_kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        timeout=timeout,
        temperature=temperature,
        model_kwargs=model_kwargs,
    )


class AgentGraphRuntime:
    @staticmethod
    def invoke_text_response_sync(messages: list[dict], *, timeout: int = 25, temperature: float = 0.7) -> Optional[str]:
        model = _build_chat_model(timeout=timeout, temperature=temperature)
        if model is None:
            return None

        try:
            response = model.invoke(_to_langchain_messages(messages))
        except Exception:
            return None

        content = _content_to_text(response.content)
        return content or None

    @staticmethod
    async def invoke_text_response(messages: list[dict], *, timeout: int = 25, temperature: float = 0.7) -> Optional[str]:
        model = _build_chat_model(timeout=timeout, temperature=temperature)
        if model is None:
            return None

        try:
            response = await model.ainvoke(_to_langchain_messages(messages))
        except Exception:
            return None

        content = _content_to_text(response.content)
        return content or None

    @staticmethod
    def invoke_json_response_sync(messages: list[dict], *, timeout: int = 30, temperature: float = 0.4) -> Optional[dict]:
        model = _build_chat_model(timeout=timeout, temperature=temperature, json_mode=True)
        if model is None:
            return None

        try:
            response = model.invoke(_to_langchain_messages(messages))
            content = _content_to_text(response.content)
            return json.loads(content)
        except Exception:
            return None

    @staticmethod
    async def invoke_json_response(messages: list[dict], *, timeout: int = 30, temperature: float = 0.4) -> Optional[dict]:
        model = _build_chat_model(timeout=timeout, temperature=temperature, json_mode=True)
        if model is None:
            return None

        try:
            response = await model.ainvoke(_to_langchain_messages(messages))
            content = _content_to_text(response.content)
            return json.loads(content)
        except Exception:
            return None

    @staticmethod
    async def _load_chat_context(state: AgentChatState) -> AgentChatState:
        agent = _agent_services()
        context, tools_used = await agent._build_context_bundle(state["assignment"], state["payload"])
        return {
            "context": context,
            "tools_used": tools_used,
            "steps": _append_step(state, "load_context"),
        }

    @staticmethod
    async def _prepare_chat_artifacts(state: AgentChatState) -> AgentChatState:
        agent = _agent_services()
        artifacts: list[dict] = []
        assignment = state["assignment"]
        payload = state["payload"]
        thread_id = state["thread"]["_id"]
        context = state.get("context", {})

        if assignment["agent_type"] == "course_builder" and agent._supports_curriculum_draft_request(payload.message):
            artifact = await agent._create_curriculum_draft_artifact(assignment, context, payload.message, thread_id=thread_id)
            if artifact:
                artifacts.append(agent._serialize_artifact(artifact))

        if assignment["agent_type"] == "progress_analyst" and agent._supports_planning_note_request(payload.message):
            artifact = await agent._create_planning_note_artifact(assignment, context, payload.message, thread_id=thread_id)
            if artifact:
                artifacts.append(agent._serialize_artifact(artifact))

        return {
            "artifacts": artifacts,
            "steps": _append_step(state, "prepare_artifacts"),
        }

    @staticmethod
    async def _build_controlled_reply(state: AgentChatState) -> AgentChatState:
        agent = _agent_services()
        reply = None
        if state["assignment"]["agent_type"] == "course_builder":
            reply = await agent._build_controlled_course_builder_reply(
                state["assignment"],
                state["payload"].message,
                state.get("context", {}),
                state.get("history", []),
                state["thread"]["_id"],
                state["current_user"],
            )
        elif state["assignment"]["agent_type"] == "lesson_tutor":
            reply = agent._build_controlled_lesson_tutor_reply(
                state["payload"].message,
                state.get("context", {}),
            )
        return {
            "controlled_reply": reply,
            "steps": _append_step(state, "controlled_reply"),
        }

    @staticmethod
    def _route_after_controlled_reply(state: AgentChatState) -> str:
        return "finalize_chat_reply" if state.get("controlled_reply") else "generate_llm_reply"

    @staticmethod
    async def _generate_llm_reply(state: AgentChatState) -> AgentChatState:
        agent = _agent_services()
        messages = agent._build_openai_messages(
            state["assignment"]["agent_type"],
            state.get("context", {}),
            state.get("history", []),
            state["payload"].message,
        )
        content = await AgentGraphRuntime.invoke_text_response(messages, timeout=25, temperature=0.7)
        ai_reply = (
            {
                "content": content,
                "metadata": {
                    "provider": "openai",
                    "model": OPENAI_MODEL,
                },
            }
            if content
            else None
        )
        return {
            "ai_reply": ai_reply,
            "steps": _append_step(state, "generate_llm_reply"),
        }

    @staticmethod
    async def _finalize_chat_reply(state: AgentChatState) -> AgentChatState:
        agent = _agent_services()
        reply = state.get("controlled_reply") or state.get("ai_reply")
        if reply is None:
            deterministic = agent._deterministic_reply(
                state["assignment"]["agent_type"],
                state["payload"].message,
                state.get("context", {}),
            )
            if deterministic:
                reply = {
                    "content": deterministic,
                    "metadata": {"provider": "deveda-deterministic"},
                }
            else:
                reply = {
                    "content": agent._fallback_reply(
                        state["assignment"]["agent_type"],
                        state["payload"].message,
                        state.get("context", {}),
                    ),
                    "metadata": {"provider": "deveda-fallback"},
                }

        metadata = dict(reply.get("metadata") or {})
        metadata["toolsUsed"] = state.get("tools_used", [])
        metadata["orchestrator"] = "langgraph"

        artifacts = state.get("artifacts", [])
        if artifacts:
            metadata["artifacts"] = artifacts
            if len(artifacts) == 1 and artifacts[0]["title"] not in reply["content"]:
                reply["content"] += f"\n\nI also created: {artifacts[0]['title']}."

        if state["assignment"]["agent_type"] == "platform_support" and "route" not in metadata:
            navigation = agent._platform_navigation_reply(state["payload"].message, state.get("context", {}))
            if navigation:
                message_tokens = agent._token_set(state["payload"].message)
                for area in state.get("context", {}).get("areas", []):
                    area_tokens = agent._token_set(f"{area['name']} {area['description']}")
                    if message_tokens & area_tokens:
                        metadata["route"] = area["route"]
                        metadata["routeLabel"] = f"Open {area['name']}"
                        break

        return {
            "ai_reply": {
                "content": reply["content"],
                "metadata": metadata,
            },
            "steps": _append_step(state, "finalize_chat_reply"),
        }

    @staticmethod
    async def _load_action_context(state: AgentActionState) -> AgentActionState:
        agent = _agent_services()
        payload = state["payload"]
        assignment = state["assignment"]
        context_payload = agent.AgentMessageCreate(
            message=payload.instruction or payload.actionType,
            courseSlug=payload.courseSlug or assignment.get("course_slug"),
            lessonSlug=payload.lessonSlug or assignment.get("lesson_slug"),
        )
        context, _ = await agent._build_context_bundle(assignment, context_payload)
        if isinstance(payload.draftPayload, dict):
            context["draftPayload"] = payload.draftPayload
        if payload.lessonSlug or assignment.get("lesson_slug"):
            context["requestedLessonSlug"] = payload.lessonSlug or assignment.get("lesson_slug")
        return {
            "context": context,
            "steps": _append_step(state, "load_context"),
        }

    @staticmethod
    async def _execute_action(state: AgentActionState) -> AgentActionState:
        agent = _agent_services()
        artifact = await agent._execute_agent_action_from_context(
            state["assignment"],
            state["payload"],
            state.get("context", {}),
            state["current_user"],
        )
        return {
            "artifact": artifact,
            "steps": _append_step(state, "execute_action"),
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _chat_graph():
        workflow = StateGraph(AgentChatState)
        workflow.add_node("load_chat_context", AgentGraphRuntime._load_chat_context)
        workflow.add_node("prepare_chat_artifacts", AgentGraphRuntime._prepare_chat_artifacts)
        workflow.add_node("build_controlled_reply", AgentGraphRuntime._build_controlled_reply)
        workflow.add_node("generate_llm_reply", AgentGraphRuntime._generate_llm_reply)
        workflow.add_node("finalize_chat_reply", AgentGraphRuntime._finalize_chat_reply)

        workflow.add_edge(START, "load_chat_context")
        workflow.add_edge("load_chat_context", "prepare_chat_artifacts")
        workflow.add_edge("prepare_chat_artifacts", "build_controlled_reply")
        workflow.add_conditional_edges(
            "build_controlled_reply",
            AgentGraphRuntime._route_after_controlled_reply,
            {
                "generate_llm_reply": "generate_llm_reply",
                "finalize_chat_reply": "finalize_chat_reply",
            },
        )
        workflow.add_edge("generate_llm_reply", "finalize_chat_reply")
        workflow.add_edge("finalize_chat_reply", END)
        return workflow.compile()

    @staticmethod
    @lru_cache(maxsize=1)
    def _action_graph():
        workflow = StateGraph(AgentActionState)
        workflow.add_node("load_action_context", AgentGraphRuntime._load_action_context)
        workflow.add_node("execute_action", AgentGraphRuntime._execute_action)
        workflow.add_edge(START, "load_action_context")
        workflow.add_edge("load_action_context", "execute_action")
        workflow.add_edge("execute_action", END)
        return workflow.compile()

    @staticmethod
    async def run_chat(
        assignment: dict,
        thread: dict,
        payload: Any,
        current_user: dict,
        history: list[dict],
    ) -> dict:
        initial_state: AgentChatState = {
            "assignment": assignment,
            "thread": thread,
            "payload": payload,
            "current_user": current_user,
            "history": history,
            "steps": [],
            "artifacts": [],
        }
        result = await AgentGraphRuntime._chat_graph().ainvoke(initial_state)
        return {
            "reply": result.get("ai_reply"),
            "artifacts": result.get("artifacts", []),
            "steps": result.get("steps", []),
        }

    @staticmethod
    async def run_action(
        assignment: dict,
        payload: Any,
        current_user: dict,
    ) -> dict:
        initial_state: AgentActionState = {
            "assignment": assignment,
            "payload": payload,
            "current_user": current_user,
            "steps": [],
        }
        result = await AgentGraphRuntime._action_graph().ainvoke(initial_state)
        return {
            "artifact": result.get("artifact"),
            "steps": result.get("steps", []),
        }
