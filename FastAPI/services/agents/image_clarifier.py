# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import base64
import os
import sys
import json
from dotenv import load_dotenv
from tavily import TavilyClient
from openai import OpenAI
import requests
import warnings
import logging
import google.generativeai as genai

# Supprime l'alerte NotOpenSSLWarning pour avoir un JSON propre en sortie
warnings.filterwarnings("ignore", category=UserWarning, module='urllib3')
# Optionnel : supprime aussi les logs de debug d'OpenAI/HTTP
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

# --- CONFIGURATION ---
load_dotenv()


class ImageClarifierAgent:
    def __init__(self):
        print("🔍 Initialisation de l'ImageClarifierAgent...")
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.default_model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:7b")
        self.default_vision_model = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5-coder:7b")

        self.tavily = None
        self.openai = None

        if self.tavily_key:
            self.tavily = TavilyClient(api_key=self.tavily_key)
        else:
            print("⚠️ Warning: TAVILY_API_KEY missing. Search disabled.")

        if self.openai_key:
            self.openai = OpenAI(api_key=self.openai_key)
        else:
            print("ℹ️ Mode Local actif : Ollama configuré sur " + self.ollama_url)

    def is_available(self):
        # Toujours disponible grâce au support du modèle local Ollama
        return True

    def _encode_image(self, image_path_or_bytes):
        if isinstance(image_path_or_bytes, bytes):
            return base64.b64encode(image_path_or_bytes).decode('utf-8')
        with open(image_path_or_bytes, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_original_image(self, image_input, remark="",
                               system_role="You are an expert instructor. Analyze the core concept of this image.",
                               model_name=None):
        """ ÉTAPE 1 : Analyse technique de l'image source avec le rôle du professeur et le modèle scellé. """
        if model_name is None:
            model_name = self.default_model

        try:
            base64_image = self._encode_image(image_input)

            # Prompt orienté description pédagogique
            user_prompt = "Décris avec précision les caractéristiques visuelles et les concepts clés de cette image. "
            if remark:
                user_prompt += f"\n\nQUESTION DE L'ÉTUDIANT : {remark}\nRéponds de manière pédagogique en te basant sur l'image."

            if "gemini" in model_name.lower():
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel(model_name)
                
                if isinstance(image_input, bytes):
                    img_data = image_input
                else:
                    with open(image_input, "rb") as f:
                        img_data = f.read()
                
                contents = [
                    user_prompt,
                    {"mime_type": "image/jpeg", "data": img_data}
                ]
                
                response = model.generate_content(
                    contents,
                    generation_config=genai.types.GenerationConfig(max_output_tokens=1000)
                )
                return response.text

            elif "gpt" in model_name.lower() and self.openai:
                expert_role = system_role
                if "diagnostic" not in expert_role.lower():
                    expert_role += " Focus on providing educational descriptions of technical or visual findings."

                response = self.openai.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": expert_role},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]}
                    ],
                    max_tokens=1000
                )
                return response.choices[0].message.content
            
            else:
                # Modèle local via Ollama (économe en RAM)
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                payload = {
                    "model": model_name,
                    "prompt": f"{system_role}\n\n{user_prompt}",
                    "stream": False,
                    "images": [base64_image]
                }
                
                resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
                if resp.status_code == 200:
                    return resp.json().get("response", "Analyse de l'image effectuée.")
                return f"Erreur modèle local Ollama : {resp.status_code}"

        except Exception as e:
            return f"Analyse pédagogique du visuel : Schéma conceptuel du cours ({str(e)})"

    def refine_search_query(self, student_remark, visual_analysis, metadata="", model_name=None):
        """ ÉTAPE 2 : Génération de mots-clés de haute précision selon l'analyse. """
        if model_name is None:
            model_name = self.default_model

        prompt = f"""
        [CONTEXT] 
        Vision Analysis: {visual_analysis} 
        Original Caption/Metadata: {metadata}
        Student Question: {student_remark}

        [TASK] Convert this analysis and metadata into a precise SEARCH QUERY to find a better, clearer, or real-world equivalent image for the student.
        [RULES]
        - Extract the most important technical keywords.
        - The query must be optimized for an image search engine.
        - Keywords ONLY. English ONLY.
        - Exclude terms like -illustration -drawing -sketch if a real-world equivalent is better.
        - Output keywords on ONE SINGLE LINE, separated by commas.
        - No bullet points, no dashes.
        - Max 200 characters.
        """
        
        try:
            if "gemini" in model_name.lower():
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(f"System: You are an expert search strategist.\n\nUser: {prompt}")
                return response.text.strip().replace('"', '')
                
            elif "gpt" in model_name.lower() and self.openai:
                response = self.openai.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system",
                         "content": "You are an expert search strategist. You convert complex descriptions into concise image search keywords. No prose."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip().replace('"', '')
            else:
                # Modèle local via Ollama
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                payload = {"model": model_name, "prompt": prompt, "stream": False}
                resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
                if resp.status_code == 200:
                    return resp.json().get("response", student_remark).strip().replace('"', '')
                return student_remark
        except Exception as e:
            print(f"⚠️ Erreur raffinement ({model_name}) : {e}")
            return student_remark # Fallback sur la remarque de l'étudiant

    def search_alternative_images(self, query):
        """Recherche des images cliniques alternatives via Tavily."""
        print(f"🌍 [ImageClarifier] Recherche Tavily pour : '{query}'")
        if not self.tavily:
            print("⚠️ [ImageClarifier] Client Tavily non initialisé")
            return []
        
        try:
            # Tavily search avec include_images=True retourne une liste d'URLs dans la clé 'images'
            results = self.tavily.search(query=query, search_depth="advanced", include_images=True, max_results=5)
            raw_images = results.get('images', [])
            print(f"📥 [ImageClarifier] Tavily a trouvé {len(raw_images)} images")
            
            # Filtre basique sur les extensions connues
            images = [img for img in raw_images if any(img.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])]
            
            # Fallback : si aucun filtre ne passe (certaines URLs n'ont pas d'extension), on prend les 3 premières
            if not images and raw_images:
                print("⚠️ [ImageClarifier] Aucun lien direct d'image détecté, utilisation des liens bruts")
                images = raw_images[:3]
            
            print(f"🖼️ [ImageClarifier] Images finales retenues : {len(images)}")
            return images
        except Exception as e:
            print(f"❌ [ImageClarifier] Erreur lors de la recherche Tavily : {e}")
            return []

    def process_clarification(self, student_remark, image_input, mongo_file_id=None, metadata=""):
        print(f"🔍 [ImageClarifier] Début du traitement - Remarque: '{student_remark}'")
        
        custom_sources = []
        system_role = "You are an expert instructor. Analyze the core concept of this image."
        model_name = "gpt-4o-mini"

        # 1. Contexte MLOps / MongoDB
        if mongo_file_id:
            try:
                from pymongo import MongoClient
                from bson import ObjectId
                _URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
                client = MongoClient(_URI, serverSelectionTimeoutMS=2000)
                db = client["course_db"]
                doc = db["documents"].find_one({"_id": ObjectId(mongo_file_id)})
                if doc:
                    system_role = doc.get("system_role", system_role)
                    custom_sources = doc.get("custom_sources", [])
                    version_id = doc.get("mlops_version_id")
                    if version_id:
                        config = db["mlops_versions"].find_one({"_id": version_id})
                        if config and config.get("llm_model"):
                            model_name = config.get("llm_model")
                            print(f"📌 [MLOps] Modèle verrouillé détecté : {model_name}")
            except Exception as e:
                print(f"⚠️ [ImageClarifier] Erreur contexte DB : {e}")

        # 2. Analyse de l'image originale (Vision)
        print("🧠 [ImageClarifier] Étape 1 : Analyse Vision de l'image originale...")
        visual_analysis = self.analyze_original_image(
            image_input,
            remark=student_remark,
            system_role=system_role,
            model_name=model_name
        )
        print(f"👁️ [ImageClarifier] Analyse vision complétée ({len(visual_analysis) if visual_analysis else 0} chars)")

        # 3. Raffinement de la requête
        print("🔧 [ImageClarifier] Étape 2 : Raffinement de la requête...")
        refined_query = self.refine_search_query(
            student_remark,
            visual_analysis,
            metadata=metadata,
            model_name=model_name
        )
        print(f"🎯 [ImageClarifier] Requête générée : '{refined_query}'")

        # 4. Construction de la requête finale (avec filtres de domaine si présents)
        domain_filters = ""
        if custom_sources:
            domains = []
            for s in custom_sources:
                clean_domain = s.split('//')[-1].split('/')[0]
                domains.append(f"site:{clean_domain}")
            domain_filters = f" ({' OR '.join(domains)}) "

        max_req_len = 390 - len(domain_filters)
        full_query = f"{refined_query[:max_req_len]}{domain_filters}"

        # 5. Recherche d'images alternatives
        print("🚀 [ImageClarifier] Étape 3 : Recherche d'images alternatives...")
        images = self.search_alternative_images(full_query)

        return {
            "status": "success",
            "student_remark": student_remark,
            "context_understood": visual_analysis,
            "search_query": refined_query,
            "found_images": images[:3]
        }

        return {
            "status": "success",
            "student_remark": student_remark,
            "context_understood": visual_analysis,
            "search_query": refined_query,
            "found_images": images[:3]
        }

    def analyze_selected_image(self, image_url, student_remark, context_analysis,
                               course_text="", concept="", model_name=None):
        """
        Analyse une image spécifique choisie et validée par le professeur pour donner
        une explication pédagogique sur-mesure reliant le cours projeté, le concept enseigné
        et la difficulté exprimée par l'étudiant.
        Fonctionne en priorité avec le modèle local économe en RAM (Ollama).
        """
        if not model_name:
            model_name = os.getenv("OLLAMA_LLM_MODEL", self.default_model)

        # Récupération de l'image (téléchargement sécurisé en Base64)
        base64_img = None
        try:
            resp = requests.get(image_url, timeout=10, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                base64_img = base64.b64encode(resp.content).decode('utf-8')
        except Exception as e:
            print(f"⚠️ Téléchargement de l'image sélectionnée échoué : {e}")

        # Construction du prompt pédagogique reliant le cours, l'image et l'étudiant
        prompt = f"""
Tu es un enseignant bienveillant et hautement pédagogue.

[SUPPORT DU COURS ACTUELLEMENT PROJETÉ]
{course_text or "Support de cours affiché sur la diapositive en classe."}

[CONCEPT CLÉ DU COURS]
{concept or "Concept théorique enseigné par le professeur."}

[ANALYSE DU SCHÉMA / VISUEL DE LA DIAPOSITIVE ORIGINALE]
{context_analysis or "Illustration originale du cours."}

[INCOMPRÉHENSION EXPRIMÉE PAR L'ÉTUDIANT]
"{student_remark}"

[SITUATION PÉDAGOGIQUE]
L'étudiant n'a pas compris ce que représentait l'image de la diapositive en relation avec le cours et le concept projeté.
Le professeur vient de valider et sélectionner une NOUVELLE image alternative plus claire pour l'ensemble des étudiants.

[TA MISSION]
Rédige une explication pédagogique limpide et vivante en français pour les étudiants :
1. Rappelle en une phrase simple ce que la diapositive originale cherchait à illustrer.
2. Explique précisément comment cette nouvelle image validée par le professeur rend le concept plus clair et concret.
3. Fais le lien direct entre le visuel et la notion du cours pour lever tout doute chez l'étudiant.

Consignes :
- Ton chaleureux, encourageant et directement compréhensible.
- Pas de jargon superflu.
- Maximum 8 à 12 lignes.
"""

        try:
            # 1. Utilisation du modèle local (Ollama) si modèle local ou si OpenAI absent
            if "gpt" not in model_name.lower() or not self.openai:
                ollama_url = os.getenv("OLLAMA_URL", self.ollama_url)
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False
                }
                if base64_img:
                    payload["images"] = [base64_img]

                resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
                if resp.status_code == 200:
                    ans = resp.json().get("response", "").strip()
                    if ans:
                        return ans
                print(f"⚠️ Ollama status code {resp.status_code if 'resp' in locals() else 'error'}, fallback standard.")

            # 2. Utilisation d'OpenAI si configuré et explicitement demandé
            if self.openai:
                content_payload = [{"type": "text", "text": prompt}]
                if base64_img:
                    content_payload.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
                    })

                response = self.openai.chat.completions.create(
                    model=model_name if "gpt" in model_name.lower() else "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Tu es un assistant pédagogique expert qui explique les concepts visuels aux étudiants."},
                        {"role": "user", "content": content_payload}
                    ],
                    max_tokens=600
                )
                return response.choices[0].message.content.strip()

            # 3. Fallback pédagogique structuré si le modèle est occupé
            return (
                f"Cette nouvelle illustration validée par le professeur permet de mieux visualiser le concept enseigné ({concept or 'du cours'}). "
                f"Elle met en évidence les éléments clés qui n'étaient pas évidents sur le premier schéma et répond directement à la question de l'étudiant."
            )
        except Exception as e:
            return (
                f"Cette illustration validée par le professeur explicite concrètement le concept du cours en le reliant "
                f"directement aux points soulevés par l'étudiant."
            )


if __name__ == "__main__":
    # Mantain CLI compatibility for now
    if len(sys.argv) < 3:
        sys.exit(0)

    remark = sys.argv[1]
    path = sys.argv[2]
    # L'ID Mongo peut être passé en 3ème argument optionnel pour la ligne de commande
    mongo_id = sys.argv[3] if len(sys.argv) > 3 else None

    agent = ImageClarifierAgent()
    if os.path.exists(path):
        print(json.dumps(agent.process_clarification(remark, path, mongo_file_id=mongo_id)))
    else:
        print(json.dumps({"error": "File not found"}))

# --- PARTIE DU FICHIER ORIGINALE (COMMENTAIRES JAVA) ---
"""     ---     partie qui devra etre écrite dans le projet java     ---
    // Exemple schématique dans votre agent Java Étudiant
String studentRemark = "Je ne comprends pas où se situe la lésion sur cette radio";
String originalCaption = "Scanner abdominal montrant une masse hépatique";

ProcessBuilder pb = new ProcessBuilder("python3", "image_clarifier_agent.py", studentRemark, originalCaption);
Process p = pb.start();

// Lire le JSON renvoyé par Python sur la sortie standard
BufferedReader in = new BufferedReader(new InputStreamReader(p.getInputStream()));
String jsonResponse = in.readLine(); 

// Ensuite, vous envoyez ce JSON au professeur pour validation (Option B - Étape 4)
"""