import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from services.observer_agent import ObserverAgent
import os

load_dotenv()

app = FastAPI(title="Assistant AI Super Agent (J.A.R.V.I.S)")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Initialize the proactive observer agent
observer_agent = ObserverAgent()

@app.on_event("startup")
async def startup_event():
    print("🚀 Super Agent Service started on port 5006")

@app.websocket("/ws/proactive")
async def proactive_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for the J.A.R.V.I.S style proactive assistant.
    Receives continuous speech transcripts and sends back AI interventions.
    """
    await websocket.accept()
    session_id = id(websocket)
    observer_agent.register_session(session_id, websocket)
    
    try:
        while True:
            # Receive message from the frontend (transcript or commands)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            msg_type = message.get("type")
            
            if msg_type == "transcript":
                # Continuous stream of words from the professor
                text = message.get("text", "")
                current_page = message.get("current_page", 1)
                mongo_id = message.get("mongo_file_id")
                await observer_agent.process_transcript(session_id, text, current_page, mongo_id)
                
            elif msg_type == "interrupt":
                # The professor started speaking while the AI was talking
                await observer_agent.handle_interruption(session_id)
                
            elif msg_type == "speech_finished":
                # The AI finished speaking its intervention
                await observer_agent.handle_speech_finished(session_id)
                
    except WebSocketDisconnect:
        observer_agent.unregister_session(session_id)
        print(f"Client {session_id} disconnected")
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
        observer_agent.unregister_session(session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5006)
