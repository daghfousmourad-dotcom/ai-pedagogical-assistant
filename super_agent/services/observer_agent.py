import os
import json
import uuid
import asyncio
import httpx
from typing import Dict, Any
from fastapi import WebSocket
from openai import AsyncOpenAI
from services.navigation_utils import parse_navigation_command

class ObserverAgent:
    def __init__(self):
        # Dictionary to store active sessions: {session_id: {"websocket": ws, "buffer": [], "is_speaking": False, "task": None, "current_page": 1, "mongo_id": None}}
        self.sessions: Dict[int, Dict[str, Any]] = {}
        # We use the AsyncOpenAI client to avoid blocking the event loop
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # Configurable thresholds
        self.silence_threshold_seconds = 3.5 # Slightly faster
        self.buffer_max_words = 150
        self.fastapi_url = "http://127.0.0.1:5005"

    def register_session(self, session_id: int, websocket: WebSocket):
        self.sessions[session_id] = {
            "websocket": websocket,
            "buffer": [],  # List of transcript segments
            "is_speaking": False, # True if the AI is currently talking
            "evaluation_task": None, # Background task evaluating the buffer
            "current_page": 1,
            "mongo_id": None
        }
        print(f"Session {session_id} registered for proactive observation.")

    def unregister_session(self, session_id: int):
        if session_id in self.sessions:
            task = self.sessions[session_id].get("evaluation_task")
            if task and not task.done():
                task.cancel()
            del self.sessions[session_id]

    async def _evaluate_context_and_intervene(self, session_id: int):
        """
        Background task that runs when silence is detected.
        It analyzes the context buffer and decides whether to intervene.
        """
        session = self.sessions.get(session_id)
        if not session or not session["buffer"]:
            return

        # Combine all recent transcripts into one context string
        context = " ".join(session["buffer"][-self.buffer_max_words:])
        
        # Stop evaluation if the professor has barely said anything
        if len(context.split()) < 4:
             return

        # 0. Check for DIRECT NAVIGATION COMMANDS first (Fast Track)
        # On essaie d'abord de voir si c'est un ordre de navigation
        current_page = session.get("current_page", 1)
        
        nav_decision = parse_navigation_command(context, current_page)
        
        if nav_decision and nav_decision.get("action") in ("JUMP", "SCROLL"):
             target = nav_decision.get("target_page")
             print(f"🎯 Proactive Navigation detected: {nav_decision}")
             await session["websocket"].send_json({
                 "type": "intervention",
                 "text": f"Très bien, je passe à la page {target}.",
                 "navigation": nav_decision
             })
             session["is_speaking"] = True # For simplicity, treat as speaking to avoid overlapping
             session["buffer"].clear()
             return

        print(f"Evaluating context for proactive intervention: {context[-50:]}...")

        try:
            # 1. Ask GPT if it should intervene OR call FastAPI Orchestrator
            # We first ask GPT if it's a moment that requires intervention
            decision_prompt = f"""
Tu es l'intelligence proactive J.A.R.V.I.S. Tu écoutes le cours d'un professeur.
Voici ce que le professeur vient de dire : "{context}"

CRITÈRES D'INTERVENTION :
1. Le professeur est CLAIREMENT bloqué ou hésitant (ex: "euh...", "comment on dit...", "je ne sais plus").
2. Il y a une erreur factuelle ÉVIDENTE par rapport au sujet (ne corrige pas les fautes de frappe vocales).
3. Le professeur manifeste un besoin d'explication (ex: "est-ce que vous m'écoutez ?", "rappelle-moi ce concept").

SILENCE ABSOLU si :
- Le professeur parle normalement et fluidement.
- La transcription contient des erreurs ("jar v is", "prof esseur") mais le sens reste clair.
- Le professeur pose une question aux étudiants (n'y réponds pas).

Réponds par OUI ou NON uniquement.
"""
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": decision_prompt}],
                max_tokens=10,
                temperature=0.1
            )
            
            decision = response.choices[0].message.content.strip().upper()

            if "OUI" in decision:
                print(f"Proactive intervention triggered for session {session_id}")
                
                # 2. Call FastAPI Orchestrator to get a RAG-based response
                async with httpx.AsyncClient() as client:
                    try:
                        orch_res = await client.post(
                            f"{self.fastapi_url}/api/ai/orchestrate",
                            json={
                                "command": "NAVIGATE",
                                "mongo_file_id": mongo_id,
                                "current_page": current_page,
                                "speech_text": context,
                                "role": "PROFESSOR"
                            },
                            timeout=10.0
                        )
                        
                        if orch_res.status_code == 200:
                            data = orch_res.json()
                            if data.get("type") == "NAVIGATE_RESULT":
                                nav_data = data.get("data", {})
                                intervention_text = nav_data.get("text")
                                
                                if not intervention_text:
                                    # Fallback if no text but RAG found something
                                    intervention_text = "J'ai trouvé des informations pertinentes dans votre cours à ce sujet."

                                # Check if session is still valid and AI hasn't been interrupted
                                if session_id in self.sessions and not self.sessions[session_id]["is_speaking"]:
                                    # 3. Generate audio using OpenAI TTS
                                    audio_res = await self.openai_client.audio.speech.create(
                                        model="tts-1",
                                        voice="nova",
                                        response_format="mp3",
                                        input=intervention_text
                                    )
                                    
                                    os.makedirs("uploads", exist_ok=True)
                                    audio_filename = f"tts_proactive_{uuid.uuid4().hex}.mp3"
                                    audio_path = os.path.join("uploads", audio_filename)
                                    audio_res.stream_to_file(audio_path)
                                            
                                    audio_url = f"http://127.0.0.1:5006/uploads/{audio_filename}"
                                    
                                    self.sessions[session_id]["is_speaking"] = True
                                    self.sessions[session_id]["buffer"].clear() # Clear buffer after speaking
                                    
                                    # Send intervention payload including navigation/RAG data
                                    await self.sessions[session_id]["websocket"].send_json({
                                        "type": "intervention",
                                        "text": intervention_text,
                                        "audioUrl": audio_url,
                                        "navigation": nav_data if nav_data.get("action") != "STAY" else None,
                                        "clarification": nav_data.get("clarification")
                                    })
                                    return
                    except Exception as api_err:
                        print(f"⚠️ FastAPI connection failed: {api_err}")

                # 4. Fallback if FastAPI failed or didn't return useful text
                # (Existing logic but refined)
                intervention_prompt = f"""
Tu es J.A.R.V.I.S. Rappelle brièvement au professeur ce qu'il cherche ou corrige l'erreur de façon TRÈS brève (1 phrase).
Le professeur a dit : "{context}"
Réponds de manière élégante et concise.
"""
                intervention_res = await self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": intervention_prompt}],
                    max_tokens=100,
                    temperature=0.7
                )
                
                intervention_text = intervention_res.choices[0].message.content.strip()
                
                # Check if session is still valid and AI hasn't been interrupted
                if session_id in self.sessions and not self.sessions[session_id]["is_speaking"]:
                    # 3. Generate audio using OpenAI TTS
                    audio_res = await self.openai_client.audio.speech.create(
                        model="tts-1",
                        voice="nova",
                        response_format="mp3",
                        input=intervention_text
                    )
                    
                    # Save audio to a temporary file locally
                    os.makedirs("uploads", exist_ok=True)
                    audio_filename = f"tts_proactive_{uuid.uuid4().hex}.mp3"
                    audio_path = os.path.join("uploads", audio_filename)
                    
                    # We need to run sync code (writing to file) or use the modern stream_to_file api
                    audio_res.stream_to_file(audio_path)
                            
                    audio_url = f"http://127.0.0.1:5006/uploads/{audio_filename}"
                    
                    self.sessions[session_id]["is_speaking"] = True
                    self.sessions[session_id]["buffer"].clear() # Clear buffer after speaking
                    
                    # Send intervention payload to frontend
                    await self.sessions[session_id]["websocket"].send_json({
                        "type": "intervention",
                        "text": intervention_text,
                        "audioUrl": audio_url
                    })
                    
        except Exception as e:
            print(f"Error during context evaluation: {e}")
        finally:
             if session_id in self.sessions:
                 self.sessions[session_id]["evaluation_task"] = None


    async def process_transcript(self, session_id: int, text: str, current_page: int = 1, mongo_id: str = None):
        """ Called every time a new word/phrase arrives from the frontend. """
        session = self.sessions.get(session_id)
        if not session:
            return

        # Update context
        session["current_page"] = current_page
        if mongo_id:
            session["mongo_id"] = mongo_id

        # If the AI is currently speaking, do not process new transcripts (until interrupted)
        if session["is_speaking"]:
            return

        # Add to buffer
        if text.strip():
            session["buffer"].append(text.strip())
            
            # Keep buffer bounded
            if len(session["buffer"]) > self.buffer_max_words:
                session["buffer"].pop(0)

        # Cancel any pending evaluation task (debounce logic)
        existing_task = session.get("evaluation_task")
        if existing_task and not existing_task.done():
            existing_task.cancel()

        # Schedule a new evaluation task to run after the silence threshold
        async def delayed_evaluation():
            try:
                await asyncio.sleep(self.silence_threshold_seconds)
                # If we survived the sleep without being cancelled, evaluate!
                await self._evaluate_context_and_intervene(session_id)
            except asyncio.CancelledError:
                # The task was cancelled because the user started speaking again before the timeout
                pass

        session["evaluation_task"] = asyncio.create_task(delayed_evaluation())

    async def handle_interruption(self, session_id: int):
        """ Called when the professor starts speaking while the AI is talking. """
        session = self.sessions.get(session_id)
        if session:
            print(f"AI Interrupted by user in session {session_id}!")
            session["is_speaking"] = False
            # Clear buffer to start fresh after an interruption
            session["buffer"].clear()

    async def handle_speech_finished(self, session_id: int):
        """ Called when the AI finishes speaking an intervention. """
        session = self.sessions.get(session_id)
        if session:
            print(f"AI finished speaking in session {session_id}")
            session["is_speaking"] = False
            # Buffer was already cleared when triggered
