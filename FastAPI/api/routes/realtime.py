import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.dependencies import get_orchestrator

router = APIRouter(tags=["Realtime"])
active_websockets = []

@router.websocket("/ws/stt")
async def websocket_stt(websocket: WebSocket):
    from services.audio.whisper_bridge import WhisperBridge
    await websocket.accept()
    bridge = WhisperBridge.get_instance()
    if not bridge.is_available():
        await websocket.send_json({"type": "ERROR", "message": "Whisper non disponible. Vérifiez l'installation de faster-whisper."})
        await websocket.close()
        return
    
    audio_buffer = bytearray()
    FLUSH_THRESHOLD_BYTES = 16000 * 2 * 1
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                audio_buffer.extend(message["bytes"])
                if len(audio_buffer) >= FLUSH_THRESHOLD_BYTES:
                    result = await bridge.async_transcribe_bytes(bytes(audio_buffer))
                    audio_buffer.clear()
                    if result.get("text"):
                        await websocket.send_json({"type": "TRANSCRIPT", **result})
            elif "text" in message:
                cmd = json.loads(message["text"])
                if cmd.get("command") == "FLUSH" and audio_buffer:
                    result = await bridge.async_transcribe_bytes(bytes(audio_buffer))
                    audio_buffer.clear()
                    await websocket.send_json({"type": "TRANSCRIPT", **result})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"❌ [STT WS] Erreur: {e}")

@router.websocket("/ws/navigation")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                command = payload.get("command")
                if command == "PING":
                    await websocket.send_json({"type": "PONG"})
                elif command == "SYNC":
                    orch = get_orchestrator()
                    session_id = str(id(websocket))
                    res = await orch.process_sync(
                        payload.get("mongo_file_id"),
                        payload.get("current_page", 1),
                        payload.get("speech_text"),
                        session_id=session_id
                    )
                    if res:
                        if res.get("type") == "NAVIGATE_RESULT":
                            await websocket.send_json({"type": "NAVIGATE_RESULT", "data": res["data"]})
                        elif res.get("type") == "SYNC_HIGHLIGHT":
                            await websocket.send_json({"type": "SYNC_HIGHLIGHT", "data": res["data"]})
                elif command == "NAVIGATE":
                    orch = get_orchestrator()
                    res = await orch.process_navigate(
                        payload.get("mongo_file_id"),
                        payload.get("current_page", 1),
                        payload.get("speech_text"),
                        payload.get("role", "PROFESSOR"),
                        payload.get("history", [])
                    )
                    if res:
                        await websocket.send_json({"type": "NAVIGATE_RESULT", "data": res})
            except Exception as e:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
