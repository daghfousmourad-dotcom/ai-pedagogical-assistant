import json
import asyncio
import traceback
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from api.dependencies import get_voice_agent, get_orchestrator
from services.utils.metrics import IA_REQUESTS_RECEIVED_TOTAL

router = APIRouter(prefix="/api/ai", tags=["Orchestration"])


@router.post("/classify-intent")
async def classify_intent_endpoint(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Aucun texte fourni"})
        agent = get_voice_agent()
        result = await asyncio.to_thread(agent.classify_intent, text)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"intent": "TEXT_QUERY", "confidence": 0.0})


@router.post("/orchestrate")
async def orchestrate_logic(request: Request):
    try:
        body = await request.body()
        if not body:
            print("⚠️ [FastAPI] Requête rejetée : Le body HTTP est complètement vide.")
            return JSONResponse(status_code=400, content={"error": "Body vide"})

        try:
            data = json.loads(body)
            print(f"📥 [FastAPI] Payload reçu de Java : {data}")  # TRÈS UTILE POUR DEBUG
        except json.JSONDecodeError as je:
            print(f"❌ [FastAPI] Erreur de lecture JSON : {str(je)}")
            return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(je)}"})

        # --- CORRECTION DE LA LECTURE DES DONNÉES ---
        command = data.get("command", "NAVIGATE")

        # On accepte mongo_file_id OU mongo_id
        mongo_id = data.get("mongo_file_id") or data.get("mongo_id")
        current_page = data.get("current_page", 1)

        # 🔑 LA CLÉ EST LÀ : On accepte speech_text, text, ou transcript
        speech_text = data.get("speech_text") or data.get("text") or data.get("transcript") or ""

        role = data.get("role", "PROFESSOR")
        history = data.get("history", [])

        if not speech_text:
            print("⚠️ [FastAPI] Aucun texte n'a été trouvé dans le JSON (speech_text, text ou transcript manquants)")
            return JSONResponse(status_code=200, content={"type": "IGNORE", "reason": "Aucun texte reconnu"})

        IA_REQUESTS_RECEIVED_TOTAL.inc()
        orch = get_orchestrator()

        if command == "SYNC":
            last_word_index = data.get("last_word_index", 0)
            session_id = data.get("session_id", "default")
            res = await orch.process_sync(mongo_id, current_page, speech_text, role, session_id, last_word_index)
            return JSONResponse(status_code=200, content=res or {"type": "IGNORE"})

        res = await orch.process_navigate(mongo_id, current_page, speech_text, role, history)
        return JSONResponse(status_code=200, content=res or {"type": "IGNORE"})

    except Exception as e:
        print(f"🔥 [FastAPI] Erreur critique : {str(e)}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})