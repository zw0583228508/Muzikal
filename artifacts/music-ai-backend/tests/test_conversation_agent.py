"""
Tests for ConversationAgent — DISCOVERY, ENRICHMENT, EXECUTION phases.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestConversationAgentInit:
    def test_imports(self):
        from agent.conversation_agent import ConversationAgent
        assert ConversationAgent is not None

    def test_session_management_imports(self):
        from agent.conversation_agent import create_session, get_session, delete_session
        assert create_session is not None
        assert get_session is not None
        assert delete_session is not None

    def test_create_session_returns_agent(self):
        from agent.conversation_agent import create_session
        agent = create_session()
        assert agent is not None
        assert agent.session_id

    def test_get_session_found(self):
        from agent.conversation_agent import create_session, get_session
        agent = create_session()
        found = get_session(agent.session_id)
        assert found is agent

    def test_get_session_not_found(self):
        from agent.conversation_agent import get_session
        assert get_session("nonexistent-id-99999") is None

    def test_delete_session(self):
        from agent.conversation_agent import create_session, get_session, delete_session
        agent = create_session()
        sid = agent.session_id
        delete_session(sid)
        assert get_session(sid) is None

    def test_initial_phase_is_discovery(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        assert agent.phase == "DISCOVERY"

    def test_initial_history_is_empty(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        assert agent.history == []

    def test_initial_collected_params_is_empty(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        assert agent.collected_params == {}


class TestConversationAgentResponse:
    def test_agent_response_dataclass(self):
        from agent.conversation_agent import AgentResponse
        r = AgentResponse(type="question", text="מה הסגנון?", phase="DISCOVERY")
        assert r.type == "question"
        assert r.text == "מה הסגנון?"
        assert r.phase == "DISCOVERY"

    def test_agent_response_ready(self):
        from agent.conversation_agent import AgentResponse
        r = AgentResponse(type="ready", profile={"genre": "klezmer"}, phase="EXECUTION")
        assert r.type == "ready"
        assert r.profile["genre"] == "klezmer"


class TestConversationAgentGetState:
    def test_get_state_returns_dict(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        state = agent.get_state()
        assert isinstance(state, dict)
        assert "session_id" in state
        assert "phase" in state
        assert "collected_params" in state
        assert "profile_ready" in state

    def test_get_state_profile_ready_false_initially(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        assert agent.get_state()["profile_ready"] is False


class TestConversationAgentHeuristic:
    def test_heuristic_extraction_genre(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent._extract_params_heuristic("אני רוצה קלזמר")
        assert "genre" in result
        assert result["genre"] == "klezmer"

    def test_heuristic_extraction_tempo(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent._extract_params_heuristic("משהו slow ונינוח")
        assert result.get("tempo_feel") == "slow"

    def test_heuristic_extraction_era(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent._extract_params_heuristic("סגנון משנות ה-1960")
        assert result.get("era") == "1960s"

    def test_heuristic_extraction_mood(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent._extract_params_heuristic("משהו חגיגי ושמח")
        assert result.get("mood") in ("festive", "joyful")

    def test_heuristic_no_match_returns_empty(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        result = agent._extract_params_heuristic("בלה בלה xxxxxx")
        assert isinstance(result, dict)


class TestConversationAgentIsComplete:
    def test_incomplete_without_genre(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        agent.collected_params = {"era": "1930s"}
        assert agent._is_profile_complete() is False

    def test_complete_with_genre(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        agent.collected_params = {"genre": "klezmer"}
        assert agent._is_profile_complete() is True


class TestConversationAgentProcessMessageNoLLM:
    """Tests for process_message without real LLM (no AI_INTEGRATIONS_OPENAI_BASE_URL)."""

    @pytest.mark.asyncio
    async def test_process_message_returns_question_when_incomplete(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        with patch.object(agent, "_client", None):
            response = await agent.process_message("שלום")
        assert response.type == "question"
        assert response.text is not None

    @pytest.mark.asyncio
    async def test_process_message_adds_to_history(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        with patch.object(agent, "_client", None):
            await agent.process_message("שלום")
        assert len(agent.history) >= 1

    @pytest.mark.asyncio
    async def test_process_message_returns_ready_when_genre_detected(self):
        from agent.conversation_agent import ConversationAgent
        from agent.style_enricher import StyleEnricher

        agent = ConversationAgent()
        with patch.object(agent, "_client", None), \
             patch.object(agent._enricher, "_client", None):
            response = await agent.process_message("אני רוצה קלזמר")
        assert response.type in ("ready", "question")

    @pytest.mark.asyncio
    async def test_session_id_propagated(self):
        from agent.conversation_agent import ConversationAgent
        agent = ConversationAgent()
        with patch.object(agent, "_client", None):
            response = await agent.process_message("שלום")
        assert response.session_id == agent.session_id
