import os
import json
import fitz
import asyncio
import requests
import urllib3
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, Response
from qdrant_client import models
from api.dependencies import get_voice_agent, get_clarifier, get_navigator

# Désactiver les avertissements SSL pour le proxy en dév
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/api/ai", tags=["Multimedia"])
UPLOAD_DIR = "uploads"

@router.post("/tts")
async def text_to_speech_endpoint(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Aucun texte fourni"})
        agent = get_voice_agent()
        if not agent.is_available():
            return JSONResponse(content={"fallback": True})
        path = agent.text_to_speech(text, upload_dir=UPLOAD_DIR)
        if isinstance(path, str) and path.startswith("Erreur"):
            return JSONResponse(content={"fallback": True, "reason": path})
        filename = os.path.basename(path)
        return JSONResponse(status_code=200, content={"url": f"/static/uploads/{filename}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/cleanup-audio")
async def cleanup_audio_endpoint(max_age_hours: int = Query(default=24)):
    """Nettoie les fichiers audio temporaires (TTS) obsolètes pour libérer de l'espace disque."""
    try:
        agent = get_voice_agent()
        stats = agent.cleanup_expired_audio(max_age_hours=max_age_hours)
        return JSONResponse(status_code=200, content={"status": "success", "cleanup": stats})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/clarify-image")
async def clarify_image(request: Request):
    try:
        data = await request.json()
        mongo_id = data.get("mongo_file_id")
        page_num = data.get("current_page", 1)
        remark = data.get("student_remark", "").strip()
        if not mongo_id or not remark:
            return JSONResponse(status_code=400, content={"error": "Paramètres manquants"})

        nav = get_navigator()
        agent = get_clarifier()
        
        # Multi-Version Fix: Utilise la collection verrouillée de ce document
        eff_collection, _ = nav._get_effective_config(mongo_id)
        
        search_res = await asyncio.to_thread(
            nav.qdrant_client.scroll,
            collection_name=eff_collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id)),
                    models.FieldCondition(key="page_number", match=models.MatchValue(value=page_num)),
                    models.FieldCondition(key="type", match=models.MatchValue(value="individual_image"))
                ]
            ),
            limit=1
        )
        
        points = search_res[0]
        if not points:
            return JSONResponse(status_code=404, content={"error": "Aucune image trouvée sur cette page"})
            
        pdf_path = points[0].payload.get("source")
        metadata = points[0].payload.get("caption", "")
        if not pdf_path or not os.path.exists(pdf_path):
            return JSONResponse(status_code=404, content={"error": "Fichier PDF source introuvable"})

        def extract_page_image(path, p_idx):
            doc = fitz.open(path)
            page = doc[p_idx - 1]
            imgs = page.get_images()
            if not imgs: return None
            xref = imgs[0][0]
            base_img = doc.extract_image(xref)
            return base_img["image"]

        img_bytes = await asyncio.to_thread(extract_page_image, pdf_path, page_num)
        if not img_bytes:
            return JSONResponse(status_code=404, content={"error": "Impossible d'extraire l'image du PDF"})
            
        result = await asyncio.to_thread(agent.process_clarification, remark, img_bytes, mongo_file_id=mongo_id, metadata=metadata)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/proxy-image")
async def proxy_image(url: str = Query(...)):
    """Proxy pour éviter les blocages CORS et le hotlinking des images externes."""
    try:
        print(f"🖼️ [Proxy] Tentative de récupération : {url}")
        # On ignore la vérification SSL (verify=False) car beaucoup d'images sources ont des certifs bancals
        resp = await asyncio.to_thread(requests.get, url, timeout=10, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}, verify=False)
        
        if resp.status_code != 200:
            print(f"❌ [Proxy] Échec (Code {resp.status_code}) : {url}")
            return Response(status_code=resp.status_code)
            
        print(f"✅ [Proxy] Succès ({resp.headers.get('Content-Length', '?')} octets) : {url}")
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/jpeg"))
    except Exception as e:
        print(f"🔥 [Proxy] Erreur critique : {str(e)}")
        return Response(status_code=500, content=str(e))

@router.post("/explain-selected-image")
async def explain_selected_image(request: Request):
    """Analyse une image spécifique choisie par le professeur et génère une explication reliant le cours et le concept."""
    try:
        data = await request.json()
        image_url = data.get("image_url")
        student_remark = data.get("student_remark", "Question sur l'illustration du cours")
        context_analysis = data.get("context_analysis", "")
        course_text = data.get("course_text", "")
        concept = data.get("concept", "")
        mongo_file_id = data.get("mongo_file_id")
        current_page = data.get("current_page")

        if not image_url:
            return JSONResponse(status_code=400, content={"error": "Paramètre manquant : image_url requis."})

        # Si le texte du cours n'est pas fourni directement par le client, on le récupère via le navigateur
        if not course_text and mongo_file_id and current_page:
            try:
                nav = get_navigator()
                course_text = await asyncio.to_thread(nav.get_page_text, mongo_file_id, int(current_page))
            except Exception as e_nav:
                print(f"⚠️ Impossible de récupérer le texte de la page {current_page} : {e_nav}")

        agent = get_clarifier()
        explanation = await asyncio.to_thread(
            agent.analyze_selected_image, 
            image_url, 
            student_remark, 
            context_analysis,
            course_text=course_text,
            concept=concept
        )
        return JSONResponse(content={
            "explanation": explanation,
            "image_url": image_url,
            "concept": concept or "Concept du cours",
            "student_remark": student_remark
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
