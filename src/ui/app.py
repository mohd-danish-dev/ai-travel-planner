"""
Streamlit chat UI for the Singapore travel assistant.

This is a thin client: all it does is render messages and POST to the
FastAPI backend's /chat endpoint (src/backend). No LangChain, no FAISS, no
MCP code lives here — the UI knows nothing about how the answer was made.

Run with:
    streamlit run app.py
"""

import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Singapore Travel Assistant", page_icon="🌴")
st.title("🌴 Singapore Travel Assistant")
st.caption(
    "Ask about attractions, itineraries, weather, or currency conversion. "
    "Answers are grounded in a Singapore travel knowledge base plus live weather/currency data."
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def call_backend(message: str) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/chat",
        json={"session_id": st.session_state.session_id, "message": message},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def reset_conversation():
    try:
        requests.post(
            f"{BACKEND_URL}/reset",
            params={"session_id": st.session_state.session_id},
            timeout=10,
        )
    except requests.RequestException:
        pass  # best-effort; a stale session on the backend is harmless
    st.session_state.messages = []


with st.sidebar:
    st.subheader("Session")
    st.text(f"ID: {st.session_state.session_id[:8]}...")
    if st.button("Start new conversation"):
        reset_conversation()
        st.rerun()

    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=3)
        if health.ok:
            st.success("Backend connected")
        else:
            st.error("Backend unhealthy")
    except requests.RequestException:
        st.error(f"Can't reach backend at {BACKEND_URL}")

# Replay chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("meta"):
            with st.expander("Sources & tools used"):
                meta = msg["meta"]
                st.markdown(f"**Intent:** {meta['intent']}")
                if meta["sources"]:
                    st.markdown("**Sources:**")
                    for s in meta["sources"]:
                        st.markdown(f"- [{s['title']}]({s['url']})")
                if meta["tools_called"]:
                    st.markdown(f"**Tools called:** {', '.join(meta['tools_called'])}")

if user_input := st.chat_input("Ask about Singapore travel..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking... (local LLM inference can take a while)"):
            try:
                result = call_backend(user_input)
                answer = result["answer"]
                st.markdown(answer)
                with st.expander("Sources & tools used"):
                    st.markdown(f"**Intent:** {result['intent']}")
                    if result["sources"]:
                        st.markdown("**Sources:**")
                        for s in result["sources"]:
                            st.markdown(f"- [{s['title']}]({s['url']})")
                    if result["tools_called"]:
                        st.markdown(f"**Tools called:** {', '.join(result['tools_called'])}")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "meta": {
                            "intent": result["intent"],
                            "sources": result["sources"],
                            "tools_called": result["tools_called"],
                        },
                    }
                )
            except requests.RequestException as e:
                error_text = f"Couldn't reach the backend at {BACKEND_URL}: {e}"
                st.error(error_text)
                st.session_state.messages.append({"role": "assistant", "content": error_text})
