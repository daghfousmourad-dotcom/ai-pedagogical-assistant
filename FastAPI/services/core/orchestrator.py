# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import asyncio
import re
import time

import numpy as np
from fuzzywuzzy import fuzz
from typing import List, Dict, Any, Optional
from openai import OpenAI
import os
import fitz
from qdrant_client import models
import json
import requests

from services.utils.mlops_config import get_active_embedding_config, get_active_llm_config
from services.core.nav import NavigationLogic
from services.core.surlignage_v3 import HighlightLogic

class OrchestratorService:
    def __init__(self, nav, voice_agent, rag_service, clarifier_agent, redis_client=None):
        self.nav = nav
        self.voice_agent = voice_agent
        self.rag = rag_service
        self.clarifier = clarifier_agent
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.nav_logic = NavigationLogic(nav, redis_client)
        self.highlight_logic = HighlightLogic(nav)
        
        # Récupération dynamique de la config MLOps
        self.config = get_active_embedding_config()
        self.llm_config = get_active_llm_config()
        self.provider = self.llm_config.get("llm_provider", "OPENAI")
        self.model_name = self.llm_config.get("llm_model", "gpt-4o-mini")
        
        # — Session State : Redis (prioritaire) ou fallback RAM —
        # Clé Redis : "sync:{session_id}:{mongo_id}" -> JSON {page, last_word_index}
        # TTL : 3600s pour nettoyage automatique
        self.redis = redis_client  # aioredis.Redis instance (injecté depuis main.py)
        self._local_state = {}     # Fallback RAM si Redis non dispo

    # -------------------------------------------------------------------------
    # 🔑 Redis session helpers (avec fallback RAM)
    # -------------------------------------------------------------------------
    async def _get_session_state(self, session_id: str, mongo_id: str, default_page: int) -> dict:
        redis_key = f"sync:{session_id}:{mongo_id}"
        if self.redis:
            try:
                raw = await self.redis.get(redis_key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                print(f"⚠️ Redis get error: {e}")
        # Fallback RAM
        return self._local_state.get(redis_key, {"page": default_page, "last_word_index": 0})

    async def _save_session_state(self, session_id: str, mongo_id: str, state: dict):
        redis_key = f"sync:{session_id}:{mongo_id}"
        if self.redis:
            try:
                await self.redis.setex(redis_key, 3600, json.dumps(state))
                return
            except Exception as e:
                print(f"⚠️ Redis setex error: {e}")
        # Fallback RAM
        self._local_state[redis_key] = state

    # -------------------------------------------------------------------------
    # 📡 process_sync : Surlignage Qdrant + Transition de page + Redis State
    # -------------------------------------------------------------------------
    async def process_sync(self, mongo_id, current_page, speech_text, role="PROFESSOR", session_id="default", last_word_index=0):
        """
        Version 4.2 (Modulaire) : Navigation protégée + Surlignage + Rôle Stable.
        """
        # On traite maintenant les mots courts plus bas pour permettre le saut de page (Grace Period)
        # Mais on ignore les chaînes vides
        if not speech_text or not speech_text.strip():
            return {"type": "IGNORE"}

        speech_clean = speech_text.lower().strip()

        # --- RÉCUPÉRATION DE L'ÉTAT RÉEL (Redis/RAM) ---
        session_state = await self._get_session_state(session_id, mongo_id, current_page)
        
        # SI LA PAGE A CHANGÉ (ex: via bouton Java), ON RESET L'INDEX
        saved_page = session_state.get("page", current_page)
        if saved_page != current_page:
            print(f"🔄 [Sync] Changement de page détecté ({saved_page} -> {current_page}). Reset Index -> 0")
            last_word_index = 0
            # On met à jour l'état immédiatement pour éviter les boucles
            await self._save_session_state(session_id, mongo_id, {"page": current_page, "last_word_index": 0})
        else:
            last_word_index = session_state.get("last_word_index", 0)

        # --- NOUVEAU : DÉTECTION DE COMMANDE DE NAVIGATION ---
        # Mapping phonétique pour corriger les hallucinations Whisper (ex: "Sainte" pour "Cinq")
        num_map = {
            "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sainte": 5, "saint": 5,
            "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10
        }
        
        # Détection étendue : chiffres ou mots-clés numériques
        pattern = r"(?:passe|va|retourne|aller|page)\s+(?:à\s+la\s+)?(?:page\s+)?(\d+|un|deux|trois|quatre|cinq|sainte|saint|six|sept|huit|neuf|dix)"
        match = re.search(pattern, speech_clean)
        
        if match:
            raw_val = match.group(1)
            target_cmd = int(raw_val) if raw_val.isdigit() else num_map.get(raw_val)
            
            if target_cmd is not None:
                print(f"🎯 [CMD] Commande vocale détectée : Page {target_cmd}")
                return {
                    "type": "NAVIGATE_RESULT",
                    "data": {"action": "JUMP", "target_page": target_cmd, "automatic": False}
                }
        
        # --- STABILISATION DU RÔLE ---
        # Si une commande de navigation est probable, on force le rôle PROFESSOR
        nav_keywords = {"page", "suivant", "précédent", "retourne", "passe", "diapo"}
        if role == "STUDENT" and any(k in speech_clean for k in nav_keywords):
            print(f"🎭 [Role Fix] Upgrade STUDENT -> PROFESSOR (Keyword détecté)")
            role = "PROFESSOR"

        # --- FILTRE MOTS COURTS (Sauf pour le saut de page Grace Period) ---
        is_short_speech = len(speech_clean.split()) < 2
        # On ne bloque pas encore, on verra si on a besoin de traiter le saut de page plus bas.

        # 3. Tentative de saut Lexical (Fin de page)
        # On ne lance les calculs lourds QUE si le texte est assez long, SAUF si un saut est déjà prêt (Grace Period)
        coverage = 0
        last_words_ok = False
        target_page = None
        
        # Vérifier si un saut est déjà en attente de validation
        grace_key = f"jump_grace:{session_id or 'default'}:{mongo_id}:{current_page}"
        is_ready_to_jump = False
        if self.redis:
            is_ready_to_jump = await self.redis.exists(grace_key)
        else:
            is_ready_to_jump = grace_key in self._local_state

        if not is_short_speech or is_ready_to_jump:
            # Calcul de la couverture
            coverage = await self.nav_logic.calculate_coverage(mongo_id, current_page, speech_clean, session_id)
            # Vérification des 5 derniers mots
            last_words_ok = await self.nav_logic.check_last_words_read(mongo_id, current_page, speech_clean)
            # Tentative de saut Lexical
            target_page = await self.nav_logic.check_lexical_jump(mongo_id, current_page, speech_clean)

        # La barrière est franchie si (Couverture très haute >= 0.95) OU (Couverture >= 0.80 ET (mots de fin lus OU saut lexical))
        is_barrier_passed = (coverage >= 0.95) or (coverage >= 0.80 and (last_words_ok or target_page))
        # Si on est déjà "Ready", on considère la barrière passée pour vérifier le timer
        if is_ready_to_jump:
            is_barrier_passed = True

        if not is_barrier_passed:
             print(f"🛡️ [Barrier] Bloqué : Couverture {coverage:.2f} < 0.85 (ou 0.50 + LastWords/Lexical)")
        
        # --- ÉTAPE 3 : DÉCISION ET PÉRIODE DE GRÂCE ---
        next_page = current_page + 1
        # La destination privilégiée est target_page (si détectée lexicalement), sinon next_page par défaut (si barrier franchie globalement)
        selected_target = target_page if target_page else next_page
        
        if role == "PROFESSOR" and selected_target and is_barrier_passed:
            grace_key = f"jump_grace:{session_id or 'default'}:{mongo_id}:{current_page}"
            
            # Gestion de la période de grâce (2 secondes)
            if self.redis:
                ready_time = await self.redis.get(grace_key)
                if not ready_time:
                    await self.redis.setex(grace_key, 10, str(time.time()))
                    print(f"⏳ [Grace] Page p.{current_page} prête pour saut vers p.{selected_target}. Attente 1s...")
                    return {"type": "IGNORE"}
                
                elapsed = time.time() - float(ready_time)
                if elapsed < 1.0:
                    print(f"⏳ [Grace] Attente... ({elapsed:.1f}s / 1.0s)")
                    return {"type": "IGNORE"}
            else:
                # Fallback RAM si Redis absent
                if grace_key not in self._local_state:
                    self._local_state[grace_key] = time.time()
                    print(f"⏳ [Grace-RAM] Attente 1s...")
                    return {"type": "IGNORE"}
                if time.time() - self._local_state[grace_key] < 1.0:
                    return {"type": "IGNORE"}

            # --- EXÉCUTION DU SAUT ---
            print(f"🚀 [EXEC] Saut validé après délai -> p.{selected_target}")
            if self.redis:
                await self.redis.delete(f"seen_words:{session_id or 'default'}:{mongo_id}:{selected_target}")
                await self.redis.delete(grace_key)
            
            await self._save_session_state(session_id, mongo_id, {"page": selected_target, "last_word_index": 0})
            return {
                "type": "NAVIGATE_RESULT",
                "data": {"action": "JUMP", "target_page": selected_target, "automatic": True}
            }

        # --- ÉTAPE 4 : SURLIGNAGE (Indépendant) ---
        # Le service de surlignage gère désormais son propre ancrage en interne
        highlight = await self.highlight_logic.get_highlight(
            mongo_id, current_page, speech_clean, last_word_index
        )
        
        if highlight and highlight.get("index") is not None:
            best_idx = highlight["index"]
            # Mise à jour de la position de lecture pour la prochaine bribe
            await self._save_session_state(session_id, mongo_id, {"page": current_page, "last_word_index": best_idx})
            return {"type": "SYNC_HIGHLIGHT", "data": highlight}

        return {"type": "IGNORE"}




    async def _classify_intent_with_context(self, speech_text, page_text, history):
        """
        Utilise un LLM pour déterminer l'intention en fonction du texte de la page.
        Résout l'ambiguïté "Image de Docker" vs "Image à l'écran".
        """
        provider = self.provider
        
        history_summary = ""
        if history:
            history_summary = "\n".join([f"- {h['role']}: {h['content']}" for h in history[-3:]])

        prompt = f"""
            Tu es le cerveau d'un agent pédagogique interactif. Ton rôle est de comprendre l'intention de l'utilisateur.
            
            CONTEXTE DE LA PAGE ACTUELLE :
            ---
            {page_text[:2000]}
            ---
            
            HISTORIQUE RÉCENT :
            {history_summary}
            
            REQUÊTE UTILISATEUR : "{speech_text}"
            
            INTENTIONS :
            1. "NAVIGATION" : Changer de page (ex: "page suivante", "va à la page 10").
            2. "IMAGE_CLARIFICATION" : Question sur un schéma, une photo ou un élément visuel PRÉSENT physiquement à l'écran (ex: "c'est quoi cette image ?", "explique ce schéma", "je ne comprends pas ce dessin"). 
               ⚠️ IMPORTANT : Si l'utilisateur dit "cette image" en désignant l'écran, c'est IMAGE_CLARIFICATION, même si le cours parle de "Docker Images".
            3. "TECHNICAL_QUESTION" : Question sur le fond du cours, des concepts théoriques ou des définitions (ex: "C'est quoi une image Docker ?", "Explique le concept de conteneur").
            4. "TEXT_QUERY" : Chercher un mot-clé précis pour y aller (ex: de la navigation par contenu).
            
            CONSIGNE :
            - "Va à la page 2" -> NAVIGATION.
            - "Je ne comprends pas cette image" (en pointant le PDF) -> IMAGE_CLARIFICATION.
            - "C'est quoi une image Docker ?" (définition) -> TECHNICAL_QUESTION.
            - "C'est quoi ce schéma ?" -> IMAGE_CLARIFICATION.
            - "Explique-moi ce concept" -> TECHNICAL_QUESTION.
            - "Cherche 'l'introduction'" -> TEXT_QUERY.
            
            JSON :
            {{
                "intent": "NAVIGATION" | "IMAGE_CLARIFICATION" | "TECHNICAL_QUESTION" | "TEXT_QUERY",
                "is_navigation": true/false,
                "confidence": 0.0-1.0
            }}
            """
        try:
            if provider == "OLLAMA":
                import requests
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                model_name = os.getenv("OLLAMA_LLM_MODEL", "llama3.1:8b")
                payload = {"model": model_name, "prompt": prompt, "stream": False, "format": "json"}
                # Timeout augmenté à 120s pour la première charge en RAM du modèle Mac M4
                response = await asyncio.to_thread(requests.post, f"{ollama_url}/api/generate", json=payload, timeout=120)
                return json.loads(response.json()['response'])
            else:
                completion = await asyncio.to_thread(
                    self.openai_client.chat.completions.create,
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "Tu es un expert en analyse d'intention linguistique."},
                              {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                content = completion.choices[0].message.content
                if not content:
                    print("⚠️ OpenAI returned empty content in _classify_intent_with_context")
                    return self.voice_agent.classify_intent(speech_text)
                
                print(f"🤖 OpenAI content to parse (intent): {content}")
                return json.loads(content)

        except Exception as e:
            print(f"⚠️ Erreur Routeur Cognitif ({provider}) : {e}")
            # Fallback sur l'ancien système si erreur
            return self.voice_agent.classify_intent(speech_text)

    async def process_navigate(self, mongo_id, current_page, speech_text, role, conversation_history):
        """Handle navigation and AI decision logic."""
        if not speech_text:
            return {"type": "IGNORE", "reason": "Empty transcript"}

        low_text = speech_text.lower()
        
        # 1. FAST TRACK (Direct commands)
        fast_match = self._check_fast_track(low_text, current_page)
        if fast_match:
            fast_match["intent"] = "NAVIGATION"
            fast_match["role"] = role
            return {"type": "NAVIGATE_RESULT", "data": fast_match}

        # 1️⃣ CLASSIFICATION COGNITIVE (Avec contexte de page)
        page_text = ""
        try:
            page_text = self.nav.get_page_text(mongo_id, current_page)
        except: pass

        intent_result = await self._classify_intent_with_context(speech_text, page_text, conversation_history)
        
        intent = intent_result.get("intent", "TECHNICAL_QUESTION")
        is_nav_intent = intent_result.get("is_navigation", False)
        print(f"🧠 Routeur Cognitif : {intent} | Confiance: {intent_result.get('confidence', '?')}")

        # 2️⃣ RECHERCHE VECTORIELLE (DÉSACTIVÉE POUR DIAGNOSTIC)
        vector_res = {"action": "STAY", "page": current_page}
        print(f"🚫 [DIAGNOSTIC] Recherche vectorielle désactivée pour intent: {intent}")

        res = vector_res
        res["intent"] = intent
        res["role"] = role
        source = res.get("source", "semantic")

        # 3. TECHNICAL QUESTION / RAG
        if role == "STUDENT" or (role == "PROFESSOR" and intent == "TECHNICAL_QUESTION"):
            if intent == "TECHNICAL_QUESTION" or (role == "STUDENT" and intent == "TEXT_QUERY"):
                # On force STAY pour les étudiants et pour toutes les questions RAG
                res["action"] = "STAY"
                
                rag_res = await self.rag.search_and_generate(
                    speech_text, 
                    mongo_id, 
                    history=conversation_history
                )
                
                if rag_res:
                    res["text"] = rag_res.get("llmResponse")
                    res["simpleExample"] = rag_res.get("simpleExample")
                    # On garde l'info de page source mais on s'assure que le FRONT n'y jump pas 
                    # si l'action est STAY. 
                    res["source_page"] = rag_res.get("pageToDisplay")
                else:
                    res["text"] = "Je n'ai pas pu analyser la question technique."
                
                return {"type": "NAVIGATE_RESULT", "data": res}

        # 4. IMAGE CLARIFICATION
        if intent == "IMAGE_CLARIFICATION":
            res["action"] = "STAY" # Force STAY pour éviter le fantôme
            return await self._handle_image_clarification(mongo_id, current_page, speech_text, res)

        # 5. NORMAL NAVIGATION (With Progress Guard)
        if intent in ("TEXT_QUERY", "NAVIGATION"):
            if res.get("action") in ("JUMP", "SCROLL"):
                target = res.get("target_page", current_page)
                
                # Vérification de sécurité : Saut sémantique interdit si progrès faible (< 80%)
                # Sauf si c'est une commande par mot-clé explicite (keyword)
                state = await self._get_session_state("", mongo_id, current_page) # Session ID non requis pour max_idx
                max_idx = await asyncio.to_thread(self.nav.get_page_max_index, mongo_id, current_page)
                # Récupération de la couverture depuis Redis
                coverage = 0.0
                if self.redis:
                    cov_raw = await self.redis.get(f"coverage:{session_id or 'default'}:{mongo_id}:{current_page}")
                    if cov_raw: coverage = float(cov_raw)
                else:
                    coverage = self._local_state.get(f"coverage:{current_page}", 0.0)

                # Flag addressed : bypass le verrou pour un ordre manuel
                addressed = res.get("addressed", False)
                is_manual = addressed or source.startswith("keyword")
                
                # Le verrou de barrière bloque tout saut automatique sémantique si coverage < 90%
                if not addressed and source == "semantic" and coverage < 0.9 and target != current_page:
                    print(f"🛡️ [Navigate] Bloqué : Couverture insuffisante ({coverage:.2f} < 0.90) pour saut automatique.")
                    res["action"] = "STAY"
                    res["target_page"] = current_page
                    res["text"] = "Terminez votre explication sur cette page avant de passer à la suite."
                
                elif not addressed and source.startswith("keyword") and effective_progress < 0.8 and target != current_page:
                    # Même les mots-clés sont filtrés s'ils ne sont pas adressés à l'IA
                    print(f"🛡️ [Keyword] Bloqué : Mot-clé détecté sans interpellation et progrès faible ({effective_progress:.2f}).")
                    res["action"] = "STAY"
                    res["target_page"] = current_page
                    res["text"] = None # Discret
                
                if res.get("action") in ("JUMP", "SCROLL"): # Re-check après blocage potentiel
                    if source.startswith("keyword"):
                        res["text"] = f"D'accord, passage à la page {target}."
                    elif abs(target - current_page) > 2:
                        res["text"] = f"Nous arrivons page {target}."
                    else:
                        res["text"] = None
            else:
                if res.get("score", 0) < 10.0 and source == "semantic":
                     res["text"] = "Je n'ai pas trouvé cette partie. Pouvez-vous reformuler ?"
                else:
                     res["text"] = None

        return {"type": "NAVIGATE_RESULT", "data": res}

    def _check_fast_track(self, low_text, current_page):
        p_match = re.search(r"page\s+(\d+)", low_text)
        if p_match:
            target = int(p_match.group(1))
            return {"action": "JUMP", "target_page": target, "text": f"D'accord, passage à la page {target}."}
        
        if re.search(r"\b(première page|page 1|début|commencer)\b", low_text):
            return {"action": "JUMP", "target_page": 1, "text": "Très bien, retour au début."}
        if re.search(r"\b(page suivante|avance|suite)\b", low_text):
            return {"action": "JUMP", "target_page": current_page + 1, "text": f"D'accord, passage à la page {current_page + 1}."}
        if re.search(r"\b(page précédente|recule|retour)\b", low_text):
            return {"action": "JUMP", "target_page": max(1, current_page - 1), "text": f"D'accord, retour à la page {max(1, current_page - 1)}."}
        return None

    async def _handle_image_clarification(self, mongo_id, current_page, speech_text, res):
        try:
            # Multi-Version Fix: Utilise la collection verrouillée de ce document
            eff_collection, _ = self.nav._get_effective_config(mongo_id)
            
            pts, _ = await asyncio.to_thread(
                self.nav.qdrant_client.scroll,
                collection_name=eff_collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id)),
                        models.FieldCondition(key="page_number", match=models.MatchValue(value=current_page)),
                        models.FieldCondition(key="type", match=models.MatchValue(value="individual_image"))
                    ]
                ),
                limit=1
            )
            if pts:
                pdf_p = pts[0].payload.get("source")
                bbox = pts[0].payload.get("bbox")
                metadata = pts[0].payload.get("caption", "")
                i_bytes = await asyncio.to_thread(self._extract_image, pdf_p, current_page, bbox)
                if i_bytes:
                    clarif_res = await asyncio.to_thread(
                        self.clarifier.process_clarification, 
                        speech_text, 
                        i_bytes, 
                        mongo_file_id=mongo_id,
                        metadata=metadata
                    )
                    res["clarification"] = clarif_res
                    res["text"] = "L'étudiant semble avoir une question sur l'image. J'ai trouvé des visuels plus explicites."
                else:
                    res["text"] = "Je vois que vous parlez d'une image, mais je n'ai pas pu l'extraire."
            else:
                res["text"] = "Je n'ai pas trouvé d'image spécifique sur cette page."
        except Exception as ex:
            print(f"❌ Erreur clarification : {ex}")
            res["text"] = None
        return {"type": "NAVIGATE_RESULT", "data": res}

    def _extract_image(self, path, p, bbox=None):
        try:
            # Sécurité chemin : si le chemin absolu de l'indexation (ex: sur hôte) 
            # ne match pas le container, on tente de le trouver dans le dossier uploads local.
            if not os.path.exists(path):
                filename = os.path.basename(path)
                alt_path = os.path.join("uploads", filename)
                if os.path.exists(alt_path):
                    path = alt_path
                else:
                    print(f"⚠️ Fichier introuvable : {path} (et {alt_path})")
                    return None

            d = fitz.open(path)
            pg = d[p-1]
            
            if bbox:
                # Conversion en Rect fitz pour robustesse
                # bbox peut être une liste [x0, y0, x1, y1]
                rect = fitz.Rect(bbox)
                print(f"📸 Extraction précise : Page {p} | BBox: {bbox}")
                pix = pg.get_pixmap(clip=rect, dpi=200)
                return pix.tobytes("jpeg")
            
            # Fallback si pas de bbox ou si extraction ratée
            ims = pg.get_images()
            if ims:
                print(f"🖼️ Fallback : Extraction du premier objet image de la page {p}")
                return d.extract_image(ims[0][0])["image"]
            
            # Ultime recours : rendu de la page entière
            print(f"📄 Ultime recours : Rendu complet de la page {p}")
            pix = pg.get_pixmap(dpi=150)
            return pix.tobytes("jpeg")
        except Exception as e:
            print(f"❌ Erreur _extract_image (Path: {path}, Page: {p}) : {e}")
            return None
