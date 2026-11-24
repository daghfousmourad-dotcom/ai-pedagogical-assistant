// ==============================================================================
// PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
// Système d'Interaction Vocale Intelligent pour l'Éducation
// ------------------------------------------------------------------------------
// Ce fichier est confidentiel et protégé par les lois sur la propriété 
// intellectuelle. Toute diffusion non autorisée est passible de poursuites.
// ==============================================================================
import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiCall, BASE_URL } from '../services/api';
import { useSpeechRecognition } from './hooks/useSpeechRecognition'; // Assuming these hooks are available
import { useSpeechSynthesis } from './hooks/useSpeechSynthesis'; // Assuming these hooks are available

// URL directe vers le serveur FastAPI (port 5005)
const AI_BASE_URL = 'http://127.0.0.1:5005';

const SuperSession = () => {
    const { courseId, docId } = useParams();
    const location = useLocation();
    const navigate = useNavigate();
    const courseTitle = location.state?.courseTitle || 'Super IA Session (J.A.R.V.I.S)';

    // États du cours et du document
    const [courseData, setCourseData] = useState(null);
    const [messages, setMessages] = useState([]);
    const [inputQuery, setInputQuery] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const [documentMetadata, setDocumentMetadata] = useState(null);
    const [rotation, setRotation] = useState(0);
    const [isProcessing, setIsProcessing] = useState(false); // New state for processing status

    // États liés à "Voice AI" et Audio
    const { startListening, stopListening, transcript, isListening, resetTranscript } = useSpeechRecognition();
    const { speak, isAIPeaking, cancelSpeech } = useSpeechSynthesis();
    const [isSessionActive, setIsSessionActive] = useState(false);

    // Proactive WebSocket ref
    const proactiveWs = useRef(null);

    const [wsStatus, setWsStatus] = useState('connecting'); // 'connecting' | 'connected' | 'disconnected'
    const [welcomeMessage, setWelcomeMessage] = useState("");
    const [imageSuggestions, setImageSuggestions] = useState(null); // { found_images: [], context_understood: "" }
    const [selectedClarifierImage, setSelectedClarifierImage] = useState(null); // Image URL choisie
    const [clarificationExplanation, setClarificationExplanation] = useState(""); // Explication pédagogique sur-mesure de l'image
    const [isClarifierProcessing, setIsClarifierProcessing] = useState(false);
    const [highlight, setHighlight] = useState(null); // { page, bbox: [x,y,w,h] }
    const [isCalibrating, setIsCalibrating] = useState(false);
    const [profVoiceProfile, setProfVoiceProfile] = useState(null); // Empreinte acoustique simplifiée
    const [aiName, setAiName] = useState("Siri"); // Nom par défaut
    const [currentRole, setCurrentRole] = useState('PROFESSOR'); // Par défaut
    const [courseMetadata, setCourseMetadata] = useState(null); // { customSources }
    const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);
    const [newSourceUrl, setNewSourceUrl] = useState('');
    const [isWaitingForFirstPart, setIsWaitingForFirstPart] = useState(false); // Flag pour l'attente du début

    const canvasRef = useRef(null);
    const pdfDocRef = useRef(null);
    const isRenderingRef = useRef(false);
    const wsRef = useRef(null);
    const synthRef = useRef(window.speechSynthesis); // Kept for fallback/legacy, though useSpeechSynthesis is preferred
    const currentUtteranceRef = useRef(null); // Kept for fallback/legacy
    const speakTimeoutRef = useRef(null); // Kept for fallback/legacy
    const isSpeakingRef = useRef(false); // Kept for fallback/legacy
    const isInitializingRef = useRef(true);
    const isMountedRef = useRef(true);
    const reconnectTimerRef = useRef(null);
    const speechQueueRef = useRef([]);
    const audioRef = useRef(null);           // Lecteur audio HTML (TTS backend)
    const isProcessingQueueRef = useRef(false); // Verrou anti-double traitement
    // Refs miroirs pour éviter les problèmes de fermeture (closure) dans les callbacks statics
    const isSessionActiveRef = useRef(false);
    const isProcessingRef = useRef(false);
    const documentMetadataRef = useRef(null);
    const lastScrollTime = useRef(0);
    const audioContextRef = useRef(null);
    const analyzerRef = useRef(null);
    const overlayCanvasRef = useRef(null);
    const highlightTimerRef = useRef(null);
    const currentPageRef = useRef(1);
    const lastSpeechEndTimeRef = useRef(0);
    const lastViewportRef = useRef(null);
    const isListeningRef = useRef(false);
    const isCalibratingRef = useRef(false);
    const isWaitingForFirstPartRef = useRef(false);
    const waitingForCalibrationRef = useRef(false);
    const preAuthorizedStreamRef = useRef(null); // Nouveau : Flux pré-ouvert pour éviter le lag
    const lastTranscriptRef = useRef("");        // Pour déduplication
    const lastRequestTimeRef = useRef(0);        // Pour déduplication
    const messagesEndRef = useRef(null);         // Pour l'auto-scroll du chat

    // Auto-scroll pour le dialogue
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // Monitor transcript and send to proactive engine continuously
    useEffect(() => {
        if (!isListening || !transcript) {
            if (!transcript) lastTranscriptRef.current = "";
            return;
        }

        // Si le transcript est plus court que le précédent, c'est que la reco a redémarré
        if (transcript.length < lastTranscriptRef.current.length) {
            lastTranscriptRef.current = "";
        }

        const newText = transcript.substring(lastTranscriptRef.current.length).trim();
        if (newText.length > 0) {
            // SI L'IA PARLE, ON LA COUPE INSTANTANEMENT CAR LE PROF PARLE
            // Plus robuste : on n'interrompt que si le fragment est assez long (> 5 mots)
            if (isAIPeaking && newText.split(' ').length > 4) {
                console.log("🛑 Interruption de l'IA !");
                cancelSpeech();
                if (proactiveWs.current && proactiveWs.current.readyState === WebSocket.OPEN) {
                    proactiveWs.current.send(JSON.stringify({ type: "interrupt" }));
                }
            }

            // Envoyer le nouveau fragment au Super Agent
            if (proactiveWs.current && proactiveWs.current.readyState === WebSocket.OPEN) {
                proactiveWs.current.send(JSON.stringify({
                    type: "transcript",
                    text: newText,
                    current_page: currentPage,
                    mongo_file_id: docId
                }));
            }

            lastTranscriptRef.current = transcript;
        }
    }, [transcript, isListening, isAIPeaking, cancelSpeech]);

    // Cleanup and Refs
    useEffect(() => { isSessionActiveRef.current = isSessionActive; }, [isSessionActive]);
    useEffect(() => { isProcessingRef.current = isProcessing; }, [isProcessing]);

    // Synchroniser les refs avec le state (appelé à chaque rendu)
    useEffect(() => { documentMetadataRef.current = documentMetadata; }, [documentMetadata]);
    useEffect(() => { currentPageRef.current = currentPage; }, [currentPage]);
    useEffect(() => { isListeningRef.current = isListening; }, [isListening]);
    useEffect(() => { isCalibratingRef.current = isCalibrating; }, [isCalibrating]);
    useEffect(() => { isWaitingForFirstPartRef.current = isWaitingForFirstPart; }, [isWaitingForFirstPart]);

    // Initialisation
    useEffect(() => {
        // Réinitialiser le flag monté (important pour React StrictMode qui démonte/remonte)
        isMountedRef.current = true;

        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        const profName = storedUser.fullName || storedUser.email?.split('@')[0] || "Docteur";

        if (!profId) {
            navigate('/login');
            return;
        }

        // Préparer le message d'accueil pour l'overlay
        setWelcomeMessage(`Bonjour ${profName}, prêt pour votre cours sur "${courseTitle}" ?`);

        // Charger les données en arrière-plan
        initializeSession(profId);

        // Configuration WebSocket
        connectWebSocket();

        // Débloquer le micro après l'initialisation de base (3s)
        const initTimeout = setTimeout(() => {
            isInitializingRef.current = false;
            console.log("✅ Initialisation terminée");
        }, 3000);

        return () => {
            isMountedRef.current = false;
            clearTimeout(initTimeout);
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (wsRef.current) {
                wsRef.current.onclose = null; // Important pour éviter une reconnexion fantôme
                wsRef.current.close();
                wsRef.current = null;
            }
            if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
        };
    }, []);

    useEffect(() => {
        // Connect to Super Agent WebSocket
        proactiveWs.current = new WebSocket('ws://127.0.0.1:5006/ws/proactive');

        proactiveWs.current.onopen = () => {
            console.log("Connecté au Super Agent (Port 5006)");
        };

        proactiveWs.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "intervention") {
                const messageAI = {
                    id: Date.now(),
                    sender: 'ai',
                    text: data.text,
                    timestamp: new Date().toLocaleTimeString()
                };
                setMessages(prev => [...prev, messageAI]);

                // Jouer l'audio via la file d'attente pour synchronisation
                if (data.audioUrl || data.text) {
                    speak(data.text || "", {
                        onSpeechEnd: () => {
                            if (proactiveWs.current && proactiveWs.current.readyState === WebSocket.OPEN) {
                                proactiveWs.current.send(JSON.stringify({ type: "speech_finished" }));
                            }
                        }
                    });
                }

                // Gérer la NAVIGATION proactive
                if (data.navigation) {
                    const nav = data.navigation;
                    if (nav.action === "JUMP" || nav.action === "SCROLL") {
                        console.log("🚀 Super Agent jump/scroll:", nav.target_page);
                        renderPage(nav.target_page);
                    }
                }

                // Gérer la CLARIFICATION proactive
                if (data.clarification) {
                    console.log("🎨 Super Agent image suggestion:", data.clarification);
                    setImageSuggestions(data.clarification);
                }

                // Gérer le SIMPLE EXAMPLE s'il existe
                if (data.simpleExample) {
                    setMessages(prev => {
                        const newMessages = [...prev];
                        const lastMsg = newMessages[newMessages.length - 1];
                        if (lastMsg && lastMsg.sender === 'ai') {
                            lastMsg.simpleExample = data.simpleExample;
                        }
                        return newMessages;
                    });
                }
            }
        };

        return () => {
            if (proactiveWs.current) proactiveWs.current.close();
            // stopAudio(); // Assurer l'arrêt de l'audio - assuming this function exists or is handled by useSpeechSynthesis
        };
    }, []);

    const connectWebSocket = () => {
        // Éviter de créer un WS si le composant est déjà démonté
        if (!isMountedRef.current) return;

        // SÉCURITÉ : Fermer l'éventuel socket existant avant d'en créer un nouveau
        // Cela évite les doublons de messages lors des re-montages rapides (React StrictMode)
        if (wsRef.current) {
            console.log("🔄 Nettoyage WebSocket existant avant reconnexion...");
            wsRef.current.onclose = null;
            wsRef.current.onerror = null;
            wsRef.current.onmessage = null;
            wsRef.current.close();
            wsRef.current = null;
        }

        setWsStatus('connecting');
        const ws = new WebSocket('ws://127.0.0.1:8085/ws/navigation');
        wsRef.current = ws;

        ws.onopen = () => {
            if (!isMountedRef.current) {
                ws.close();
                return;
            }
            console.log("WebSocket connecté à l'Archiviste IA");
            setWsStatus('connected');
        };

        ws.onmessage = (event) => {
            if (!isMountedRef.current) return;
            try {
                const response = JSON.parse(event.data);
                if (wsRef.current !== ws) return; // Filtrage anti-stale

                if (response.type === "NAVIGATE_RESULT") {
                    const data = response.data;
                    if (data.action === "JUMP" || data.action === "SCROLL") {
                        const targetPage = data.target_page || data.page;
                        if (targetPage) scrollToPage(targetPage);
                    }
                    if (data.text) {
                        speak(data.text);
                    }

                    if (data.clarification) {
                        console.log("🎨 Suggestions d'images reçues :", data.clarification);
                        setImageSuggestions(data.clarification);
                        setIsClarifierProcessing(false);
                    }
                    if (data.simpleExample) {
                        setMessages(prev => {
                            const newMessages = [...prev];
                            const lastMsg = newMessages[newMessages.length - 1];
                            if (lastMsg && lastMsg.sender === 'ai') {
                                lastMsg.simpleExample = data.simpleExample;
                            }
                            return newMessages;
                        });
                    }
                } else if (response.type === "SYNC_HIGHLIGHT") {
                    const data = response.data;
                    if (data.page === currentPageRef.current) {
                        drawHighlight(data.bbox);
                    }
                }
            } catch (err) {
                console.error("Erreur WebSocket message:", err);
            }
        };

        ws.onclose = (e) => {
            wsRef.current = null;
            if (isMountedRef.current) {
                console.log("WebSocket déconnecté, tentative de reconnexion dans 3s...");
                setWsStatus('disconnected');
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = setTimeout(connectWebSocket, 3000);
            }
        };

        ws.onerror = (err) => {
            console.error("Erreur WebSocket:", err);
            ws.close();
        };
    };

    const startSession = async () => {
        setIsSessionActive(true);
        setIsWaitingForFirstPart(false);
        console.log("🚀 Lancement Session Active (Écoute continue)...");

        // Flash visuel ou message court pour confirmer
        speak(`Écoute active démarrée. Je suis prêt.`);
    };

    const testAudio = () => {
        console.log("🧪 Test audio manuel...");
        speak("Vérification du système audio. Si vous m'entendez, tout est prêt.");
    };

    // --- LOGIQUE J.A.R.V.I.S ---
    const startCalibration = async () => {
        setIsCalibrating(true);
        // Activer directement la session et le micro
        setIsSessionActive(true);
        setIsWaitingForFirstPart(false);
        setIsCalibrating(false);
        
        speak(`Mode Super IA activé. J'écoute en permanence.`);
        console.log("📢 Super Agent: Écoute continue démarrée...");
        
        setTimeout(() => {
            if (!isListeningRef.current) toggleListening();
        }, 1000);
    };

    const analyzeCurrentVoice = () => {
        // En mode Super IA, on ne fait pas de biométrie, on suppose que c'est le professeur
        return 'PROFESSOR';
    };

    const initializeSession = async (profId) => {
        try {
            // 0. Récupérer les métadonnées du cours (incluant les documents)
            const courseRes = await apiCall(`/api/courses/${profId}/${courseId}`);
            if (courseRes.success) {
                const courseData = courseRes.data;
                setCourseMetadata(courseData);

                // 1. Récupérer le document spécifique du cours
                const docs = courseData.documents || [];
                const targetDoc = docs.find(d => d.id === docId);

                if (targetDoc) {
                    setDocumentMetadata(targetDoc);

                    const token = localStorage.getItem('token');
                    const pdfUrl = `${BASE_URL}/api/livesession/documents/${targetDoc.id}/stream`;

                    // window.pdfjsLib is loaded globally from CDN in index.html
                    const loadingTask = window.pdfjsLib.getDocument({
                        url: pdfUrl,
                        httpHeaders: { 'Authorization': `Bearer ${token}` }
                    });

                    const pdfDoc = await loadingTask.promise;
                    pdfDocRef.current = pdfDoc;

                    // Rendu de la première page uniquement
                    renderPage(1);
                } else {
                    addMessage('ai', "Ce cours ne contient aucun document PDF à charger.");
                }
            } else {
                addMessage('ai', "Erreur lors de la récupération des données du cours.");
            }
        } catch (error) {
            console.error("Erreur initialisation session:", error);
            addMessage('ai', "Erreur lors du chargement des documents.");
        }
    };

    const renderPage = async (num, rotOffset = rotation) => {
        if (!pdfDocRef.current || !canvasRef.current) return;
        if (isRenderingRef.current) return;

        isRenderingRef.current = true;
        try {
            const safeNum = Math.max(1, Math.min(num, pdfDocRef.current.numPages));
            const page = await pdfDocRef.current.getPage(safeNum);
            const canvas = canvasRef.current;
            const ctx = canvas.getContext('2d');

            const finalRotation = (page.rotate + rotOffset) % 360;
            const viewport = page.getViewport({ scale: 1.2, rotation: finalRotation });
            lastViewportRef.current = viewport;

            canvas.height = viewport.height;
            canvas.width = viewport.width;

            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };

            await page.render(renderContext).promise;
            setCurrentPage(safeNum);
        } catch (err) {
            console.error("Erreur rendu PDF:", err);
        } finally {
            isRenderingRef.current = false;
        }
    };


    function speakAndShow(text, addMessageFlag = true) {
        if (!text) return;
        if (addMessageFlag) addMessage('ai', text);
        speak(text);
    }

    const scrollToPage = (num) => {
        renderPage(num);
    };

    // Gestion du défilement à la souris (Virtual Scroll)
    const drawHighlight = (bbox) => {
        if (!overlayCanvasRef.current || !canvasRef.current || !lastViewportRef.current) return;
        const canvas = canvasRef.current;
        const overlay = overlayCanvasRef.current;
        const viewport = lastViewportRef.current;
        const ctx = overlay.getContext('2d');

        overlay.width = canvas.width;
        overlay.height = canvas.height;

        ctx.clearRect(0, 0, overlay.width, overlay.height);

        // Conversion intelligente : on utilise le viewport de PDF.js pour transformer
        // les coord PDF [x, y, w, h] en coord canvas
        const [x0, y0, x1, y1] = bbox;

        // La méthode convertToViewportRectangle est idéale ici
        const [rx0, ry0, rx1, ry1] = viewport.convertToViewportRectangle([x0, y0, x1, y1]);

        ctx.fillStyle = "rgba(255, 255, 0, 0.35)"; // Jaune médical
        ctx.strokeStyle = "rgba(255, 165, 0, 0.7)";
        ctx.lineWidth = 1.5;

        // Note: convertToViewportRectangle retourne les points, il faut calculer largeur/hauteur
        // et attention à l'inversion possible de Y selon l'origine du PDF
        const rectX = Math.min(rx0, rx1);
        const rectY = Math.min(ry0, ry1);
        const rectW = Math.abs(rx1 - rx0);
        const rectH = Math.abs(ry1 - ry0);

        ctx.fillRect(rectX, rectY, rectW, rectH);
        ctx.strokeRect(rectX, rectY, rectW, rectH);

        // Effacer après 2 secondes
        if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
        highlightTimerRef.current = setTimeout(() => {
            ctx.clearRect(0, 0, overlay.width, overlay.height);
        }, 2000);
    };

    const handleWheel = (e) => {
        const now = Date.now();
        if (now - lastScrollTime.current < 600) return;

        if (e.deltaY > 50) {
            if (currentPage < pdfDocRef.current?.numPages) {
                lastScrollTime.current = now;
                renderPage(currentPage + 1);
            }
        } else if (e.deltaY < -50) {
            if (currentPage > 1) {
                lastScrollTime.current = now;
                renderPage(currentPage - 1);
            }
        }
    };

    const handleRotate = () => {
        const newRotation = (rotation + 90) % 360;
        setRotation(newRotation);
        renderPage(currentPage, newRotation);
    };

    const addMessage = (sender, text) => {
        setMessages(prev => [...prev, { id: Date.now() + Math.random(), sender, text }]);
    };

    const toggleListening = async () => {
        if (isListening) {
            stopListening();
        } else {
            // Arrêter la voix de l'IA si elle parle
            cancelSpeech();
            startListening();
        }
    };

    const handleVoiceCommand = (transcript, isFinal = true) => {
        // Lire les refs (toujours à jour, pas les valeurs de closure)
        if (!isSessionActiveRef.current) return;

        const role = analyzeCurrentVoice();
        setCurrentRole(role);

        // Nettoyage et normalisation du texte
        const cleanRaw = transcript.trim();
        const lowTranscript = cleanRaw.toLowerCase();

        // Commande vocale pour fermer les popups (seulement si final)
        if (isFinal && (lowTranscript.includes("fermer") || lowTranscript.includes("quitter") || lowTranscript.includes("annuler") || lowTranscript.includes("stop"))) {
            if (selectedClarifierImage || imageSuggestions) {
                setImageSuggestions(null);
                setSelectedClarifierImage(null);
                speak("C'est fermé.");
                return;
            }
        }

        // --- FILTRE D'ACTIVATION (Trigger Word) ---
        // Normalisation du nom pour gérer Siri/Série
        const normalizedAiName = aiName.toLowerCase();
        const isSiri = normalizedAiName === "siri" || normalizedAiName === "série";
        const variations = [normalizedAiName];
        if (isSiri) variations.push("siri", "série", "ciri", "syrie", "séries");

        let addressed = false;
        let triggerLength = 0;
        for (const v of variations) {
            if (lowTranscript.startsWith(v)) {
                addressed = true;
                triggerLength = v.length;
                break;
            }
        }

        const docMeta = documentMetadataRef.current;
        if (!docMeta || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

        // 1. Envoyer SYNC pour le "trait sous le mot" (Tracking) - Toujours envoyé pour suivre le cours
        wsRef.current.send(JSON.stringify({
            command: "SYNC",
            mongo_file_id: docMeta.id,
            current_page: currentPage,
            speech_text: cleanRaw,
            role: role
        }));

        // 2. Envoyer NAVIGATE seulement si :
        // - C'est un STUDENT (automatique)
        // - OU C'est le PROFESSOR et il a prononcé le nom (aiName)
        if (isFinal && transcript.split(' ').length > 1) {
            if (role === 'STUDENT' || (role === 'PROFESSOR' && addressed)) {
                // Nettoyer le nom de l'IA au début

                // Nettoyer le nom de l'IA au début
                const cleanTranscript = addressed
                    ? transcript.trim().substring(triggerLength).trim().replace(/^[,.\s]+/, '')
                    : transcript.trim();

                if (cleanTranscript.length > 2) {
                    console.log("📤 NAVIGATE envoyé — role:", role, "| addressed:", addressed, "| texte:", cleanTranscript);

                    // Si on attendait la première partie, on réinitialise le flag une fois reçu
                    if (isWaitingForFirstPart) {
                        setIsWaitingForFirstPart(false);
                    }

                    wsRef.current.send(JSON.stringify({
                        command: "NAVIGATE",
                        mongo_file_id: docMeta.id,
                        current_page: currentPage,
                        speech_text: cleanTranscript,
                        role: role
                    }));
                }
            } else if (role === 'PROFESSOR') {
                console.log("🧘 L'IA reste discrète (pas de trigger word)");
            }
        }
    };

    // Gestion de l'input textuel (fallback si on ne veut pas parler)
    const handleSendMessage = (e) => {
        e.preventDefault();
        if (!inputQuery.trim()) return;

        const query = inputQuery;
        addMessage('prof', query);
        setInputQuery('');
        handleVoiceCommand(query);
    };

    const handleAddSource = async () => {
        if (!newSourceUrl.trim() || !documentMetadata) return;
        const updatedSources = [...(documentMetadata.customSources || []), newSourceUrl];
        try {
            const res = await apiCall(`/api/courses/${courseId}/documents/${documentMetadata.id}/metadata`, 'PATCH', {
                customSources: updatedSources
            });
            if (res.success) {
                setDocumentMetadata({ ...documentMetadata, customSources: updatedSources });
                setNewSourceUrl('');
                speak("Source ajoutée avec succès.");
            }
        } catch (err) {
            alert("Erreur lors de l'ajout de la source");
        }
    };

    const handleRemoveSource = async (url) => {
        if (!documentMetadata) return;
        const updatedSources = documentMetadata.customSources.filter(u => u !== url);
        try {
            const res = await apiCall(`/api/courses/${courseId}/documents/${documentMetadata.id}/metadata`, 'PATCH', {
                customSources: updatedSources
            });
            if (res.success) {
                setDocumentMetadata({ ...documentMetadata, customSources: updatedSources });
                speakAndShow("Source supprimée.");
            }
        } catch (err) {
            alert("Erreur lors de la suppression");
        }
    };

    // --- LOGIQUE DE SÉLECTION D'IMAGE ---
    const handleSelectImage = async (imgUrl) => {
        setSelectedClarifierImage(imgUrl);
        setClarificationExplanation("");
        setIsClarifierProcessing(true);
        try {
            const res = await fetch(`${AI_BASE_URL}/api/ai/explain-selected-image`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_url: imgUrl,
                    student_remark: imageSuggestions?.student_remark || "Question sur cette image",
                    context_analysis: imageSuggestions?.context_understood || "",
                    concept: imageSuggestions?.search_query || "",
                    mongo_file_id: docId,
                    current_page: currentPage
                })
            });
            if (res.ok) {
                const data = await res.json();
                const explanation = data.explanation || `Cette illustration alternative validée par le professeur permet de mieux visualiser le concept abordé.`;
                setClarificationExplanation(explanation);
                speakAndShow(explanation);
            } else {
                const failMsg = "Voici une vue plus détaillée du concept sélectionné par le professeur.";
                setClarificationExplanation(failMsg);
                speakAndShow(failMsg);
            }
        } catch (e) {
            console.error("Erreur sélection image clarifiée:", e);
            const errMsg = "Image validée affichée.";
            setClarificationExplanation(errMsg);
            speakAndShow(errMsg);
        } finally {
            setIsClarifierProcessing(false);
        }
    };

    const handleCloseClarifier = () => {
        setImageSuggestions(null);
        setSelectedClarifierImage(null);
        setClarificationExplanation("");
    };

    return (
        <div style={styles.sessionPage}>
            {/* Barre de navigation supérieure */}
            <header style={styles.header}>
                <div style={styles.headerLeft}>
                    <button style={styles.backBtn} onClick={() => navigate('/dashboard')}>
                        ← Retour au Dashboard
                    </button>
                    <h1 style={styles.title}>Session de Cours : <span style={styles.highlight}>{courseTitle}</span></h1>
                </div>
                <div style={styles.headerRight}>
                    <div style={{
                        ...styles.statusBadge,
                        ...(wsStatus === 'connected'
                            ? {}
                            : wsStatus === 'connecting'
                                ? { color: '#f59e0b', border: '1px solid #f59e0b33', backgroundColor: '#1f1a0e' }
                                : { color: '#f1416c', border: '1px solid #f1416c33', backgroundColor: '#1f0e12' })
                    }}>
                        <span style={{
                            ...styles.statusDot,
                            backgroundColor: wsStatus === 'connected' ? '#00d084' : wsStatus === 'connecting' ? '#f59e0b' : '#f1416c',
                            boxShadow: wsStatus === 'connected' ? '0 0 8px #00d084' : wsStatus === 'connecting' ? '0 0 8px #f59e0b' : '0 0 8px #f1416c',
                        }}></span>
                        {wsStatus === 'connected' ? 'IA Connectée' : wsStatus === 'connecting' ? 'Connexion...' : 'IA Déconnectée'}
                    </div>
                    <button onClick={startCalibration} style={styles.superBtn}>
                        🚀 Démarrer la Super IA
                    </button>
                    <button
                        style={!isSessionActive ? styles.listenBtnDisabled : (isListening ? styles.listenBtnActive : styles.listenBtn)}
                        onClick={toggleListening}
                        disabled={!isSessionActive}
                    >
                        {isListening ? (
                            <><i className="fa-solid fa-stop-circle" style={{ marginRight: '8px' }}></i> Arrêter l'écoute</>
                        ) : (
                            <><i className="fa-solid fa-microphone" style={{ marginRight: '8px' }}></i> Démarrer Écoute Vocale</>
                        )}
                    </button>
                </div>
            </header>

            {/* Zone de contenu principale divisée en 2 */}
            <main style={styles.mainSplitLayout}>
                {/* Overlay Accueil IA */}
                {!isSessionActive && (
                    <div style={styles.overlay}>
                        <div style={styles.welcomeCard}>
                            <div style={styles.aiIcon}>🧠</div>
                            <h2 style={styles.welcomeTitle}>Session de Cours Intelligente</h2>
                            <p style={styles.welcomeText}>{welcomeMessage}</p>
                            <button style={styles.startBtn} onClick={startSession}>
                                <i className="fa-solid fa-play" style={{ marginRight: '10px' }}></i>
                                Commencer la session
                            </button>
                            <button
                                onClick={testAudio}
                                style={{
                                    marginTop: '20px',
                                    background: 'none',
                                    border: '1px solid #323248',
                                    color: '#666',
                                    padding: '5px 10px',
                                    borderRadius: '5px',
                                    fontSize: '0.8rem',
                                    cursor: 'pointer'
                                }}
                            >
                                <i className="fa-solid fa-vial" style={{ marginRight: '5px' }}></i> Tester l'audio (Debug)
                            </button>
                        </div>
                    </div>
                )}
                {/* PARTIE 1 : PDF Viewer (Lecture et Défilement automatique) */}
                <section style={styles.leftPanel}>
                    <div style={styles.panelHeader}>
                        <h2>📄 Fichiers Modèles du Cours</h2>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <button onClick={handleRotate} style={styles.rotateBtn} title="Faire pivoter">
                                🔄 Faire pivoter
                            </button>
                            <span style={styles.badgeInfo}>Page {currentPage} {pdfDocRef.current ? `/ ${pdfDocRef.current.numPages}` : ''}</span>
                        </div>
                    </div>
                    <div
                        style={styles.pdfViewerContainer}
                        onWheel={handleWheel}
                    >
                        {documentMetadata ? (
                            <div style={{ position: 'relative', display: 'inline-block' }}>
                                <canvas ref={canvasRef} style={styles.pdfCanvas}></canvas>
                                <canvas
                                    ref={overlayCanvasRef}
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        pointerEvents: 'none',
                                        zIndex: 5,
                                        width: '100%',
                                        height: '100%'
                                    }}
                                ></canvas>
                            </div>
                        ) : (
                            <div style={styles.pdfBlankState}>
                                <p style={{ fontSize: '3rem', margin: '0 0 1rem 0' }}>📋</p>
                                <h3>Aucun document</h3>
                                <p style={{ color: '#a1a5b7' }}>Ce cours ne possède pas encore de fichier PDF.</p>
                            </div>
                        )}
                    </div>
                </section>

                {/* Séparateur Visuel */}
                <div style={styles.divider}></div>

                {/* PARTIE 2 : Interaction RAG et Explications Multimodales */}
                <section style={styles.rightPanel}>
                    <div style={styles.panelHeader}>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <h2 style={{ margin: 0 }}>🧠 Assistant RAG</h2>
                            {documentMetadata?.courseContext && (
                                <div style={styles.courseDomain}>
                                    Spécialité : {documentMetadata.courseContext}
                                </div>
                            )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <button
                                onClick={() => setIsSourceModalOpen(true)}
                                style={{ ...styles.rotateBtn, fontSize: '0.7rem', padding: '4px 8px' }}
                            >
                                🌐 Sources Externes ({documentMetadata?.customSources?.length || 0})
                            </button>
                            <div style={{
                                ...styles.wsBadge,
                                backgroundColor: wsStatus === 'connected' ? '#00d084' : wsStatus === 'connecting' ? '#ff9f43' : '#f1416c'
                            }}></div>
                            <span style={styles.badgeText}>
                                {wsStatus === 'connected' ? 'IA Live' : wsStatus === 'connecting' ? 'Connexion...' : 'Hors-ligne'}
                            </span>

                            {profVoiceProfile ? (
                                <div style={{
                                    fontSize: '0.7rem',
                                    padding: '4px 8px',
                                    borderRadius: '8px',
                                    backgroundColor: currentRole === 'PROFESSOR' ? '#00d08422' : '#f1416c22',
                                    color: currentRole === 'PROFESSOR' ? '#00d084' : '#f1416c',
                                    fontWeight: 'bold',
                                    border: `1px solid ${currentRole === 'PROFESSOR' ? '#00d08444' : '#f1416c44'}`
                                }}>
                                    Role: {currentRole}
                                </div>
                            ) : (
                                <button onClick={startCalibration} style={{
                                    fontSize: '0.65rem',
                                    padding: '4px 8px',
                                    borderRadius: '8px',
                                    backgroundColor: '#323248',
                                    color: '#fff',
                                    border: 'none',
                                    cursor: 'pointer'
                                }}>
                                    🎙️ Calibrer Prof.
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Zone de discussion IA */}
                    <div style={styles.chatArea}>
                        {messages.length === 0 && (
                            <div style={{ textAlign: 'center', color: '#666', marginTop: '2rem' }}>
                                L'assistant est prêt à vous écouter.
                            </div>
                        )}
                        {messages.map(msg => (
                            <div key={msg.id} style={msg.sender === 'ai' ? styles.messageAI : styles.messageProf}>
                                <div style={{ marginBottom: '0.3rem', fontSize: '0.75rem', color: '#888' }}>
                                    {msg.sender === 'ai' ? '🤖 Assistant IA :' : '👤 Professeur :'}
                                </div>
                                <div style={msg.sender === 'ai' ? styles.bubbleAI : styles.bubbleProf}>
                                    {msg.text}
                                {msg.simpleExample && (
                                    <div style={{
                                        marginTop: '10px',
                                        padding: '8px',
                                        borderLeft: '3px solid #00d084',
                                        backgroundColor: 'rgba(0, 208, 132, 0.1)',
                                        fontSize: '0.85rem',
                                        fontStyle: 'italic'
                                    }}>
                                        💡 <strong>Exemple simple :</strong> {msg.simpleExample}
                                    </div>
                                )}
                                    {msg.sender === 'ai' && (
                                        <button
                                            onClick={() => speakAndShow(msg.text, false)}
                                            style={styles.replayBtn}
                                            title="Réécouter"
                                        >
                                            <i className="fa-solid fa-volume-high"></i>
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Zone de saisie clavier */}
                    <form style={styles.inputArea} onSubmit={handleSendMessage}>
                        <input
                            type="text"
                            style={styles.chatInput}
                            placeholder="Recherche vocale (cliquez sur le micro) ou tapez textuellement..."
                            value={inputQuery}
                            onChange={(e) => setInputQuery(e.target.value)}
                        />
                        <button type="submit" style={styles.sendBtn}>Envoyer</button>
                    </form>
                </section>
            </main>
            {/* --- POPUP CLARIFICATION D'IMAGE --- */}
            {imageSuggestions && !selectedClarifierImage && (
                <div style={styles.clarifierOverlay}>
                    <div style={styles.clarifierContent}>
                        <div style={styles.clarifierHeader}>
                            <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#fff', marginBottom: '0.5rem' }}>
                                🎨 Clarification d'Image suggérée
                            </h2>
                            <p style={{ color: '#b5b5c3' }}>
                                L'étudiant a posé une question sur le visuel. Voici des images alternatives correspondantes :
                            </p>
                        </div>
                        <div style={styles.clarifierGrid}>
                            {imageSuggestions.found_images.map((imgUrl, idx) => (
                                <div
                                    key={idx}
                                    style={styles.suggestionCard}
                                    onClick={() => handleSelectImage(imgUrl)}
                                    onMouseEnter={(e) => e.currentTarget.style.borderColor = '#00d084'}
                                    onMouseLeave={(e) => e.currentTarget.style.borderColor = 'transparent'}
                                >
                                    <img src={imgUrl} alt={`Sugg ${idx}`} style={styles.suggestionImage} />
                                    <div style={{ textAlign: 'center', color: '#00d084', fontSize: '0.9rem', fontWeight: '600' }}>
                                        Sélectionner l'image {idx + 1}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '2rem' }}>
                            <button style={styles.closePopBtn} onClick={handleCloseClarifier}>Ignorer et fermer</button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- VUE AGRANDIE DE L'IMAGE SÉLECTIONNÉE --- */}
            {selectedClarifierImage && (
                <div style={styles.clarifierOverlay}>
                    <div style={styles.clarifierContent}>
                        <div style={styles.largeImageContainer}>
                            <img src={selectedClarifierImage} style={styles.largeImage} alt="Clarification" />
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <h3 style={{ color: '#00d084', marginBottom: '1rem' }}>
                                {isClarifierProcessing ? "Analyse de l'image en cours..." : "💡 Explication Pédagogique du Concept"}
                            </h3>
                            <div style={{
                                color: '#d9eddf',
                                marginBottom: '2rem',
                                maxHeight: '200px',
                                overflowY: 'auto',
                                padding: '1rem',
                                backgroundColor: '#151521',
                                borderRadius: '12px',
                                textAlign: 'left',
                                fontSize: '0.95rem',
                                lineHeight: '1.6',
                                border: '1px solid #323248',
                                whiteSpace: 'pre-wrap'
                            }}>
                                {isClarifierProcessing ? (
                                    <div style={{ textAlign: 'center', padding: '1rem' }}>
                                        <i className="fa-solid fa-circle-notch fa-spin" style={{ fontSize: '2rem', color: '#00d084' }}></i>
                                    </div>
                                ) : (
                                    clarificationExplanation || "L'assistant analyse l'image..."
                                )}
                            </div>
                            <button style={styles.closePopBtn} onClick={handleCloseClarifier}>Fermer l'explication</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Modal de gestion des Sources Externes */}
            {isSourceModalOpen && (
                <div style={styles.modalOverlay}>
                    <div style={styles.sourceModal}>
                        <div style={styles.modalHeader}>
                            <h3>🌐 Sources de Recherche Externes</h3>
                            <button onClick={() => setIsSourceModalOpen(false)} style={styles.closeModalBtn}>✖</button>
                        </div>
                        <p style={{ fontSize: '0.8rem', color: '#a1a5b7', marginBottom: '1rem' }}>
                            L'IA utilisera ces liens en priorité pour clarifier des images ou schémas complexes.
                        </p>
                        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
                            <input
                                type="text"
                                placeholder="Coller un lien (ex: https://moodle.com...)"
                                value={newSourceUrl}
                                onChange={(e) => setNewSourceUrl(e.target.value)}
                                style={styles.chatInput}
                            />
                            <button onClick={handleAddSource} style={styles.sendBtn}>Ajouter</button>
                        </div>
                        <div style={{ flex: 1, overflowY: 'auto' }}>
                            {documentMetadata?.customSources?.length === 0 ? (
                                <p style={styles.emptyText}>Aucune source personnalisée.</p>
                            ) : (
                                documentMetadata?.customSources?.map((url, i) => (
                                    <div key={i} style={styles.sourceItem}>
                                        <a 
                                            href={url.startsWith('http') ? url : `https://${url}`} 
                                            target="_blank" 
                                            rel="noopener noreferrer" 
                                            style={{ ...styles.sourceUrl, color: '#3699ff', textDecoration: 'underline', cursor: 'pointer' }}
                                        >
                                            {url}
                                        </a>
                                        <button onClick={() => handleRemoveSource(url)} style={styles.removeSourceBtn}>🗑️</button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const styles = {
    sessionPage: {
        backgroundColor: '#0d0d14',
        height: '100vh',
        overflow: 'hidden',
        color: '#ffffff',
        fontFamily: 'Inter, sans-serif',
        display: 'flex',
        flexDirection: 'column',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '1rem 2rem',
        backgroundColor: '#151521',
        borderBottom: '1px solid #2b2b40',
        zIndex: 10,
    },
    headerLeft: {
        display: 'flex',
        alignItems: 'center',
        gap: '2rem',
    },
    headerRight: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.5rem',
    },
    backBtn: {
        backgroundColor: 'transparent',
        color: '#a1a5b7',
        border: '1px solid #2b2b40',
        padding: '0.5rem 1rem',
        borderRadius: '8px',
        cursor: 'pointer',
        fontWeight: '500',
        transition: 'all 0.2s',
    },
    superBtn: {
        backgroundColor: '#8b5cf6',
        color: 'white',
        border: 'none',
        padding: '0.8rem 1.5rem',
        borderRadius: '8px',
        fontWeight: 'bold',
        cursor: 'pointer',
        fontSize: '1rem',
        boxShadow: '0 0 15px rgba(139, 92, 246, 0.4)',
        transition: 'all 0.3s ease'
    },
    rotateBtn: {
        backgroundColor: '#2b2b40',
        color: '#a1a5b7',
        border: '1px solid #323248',
        padding: '0.6rem 1rem',
        borderRadius: '8px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        transition: 'all 0.2s',
        fontSize: '0.9rem'
    },
    title: {
        fontSize: '1.2rem',
        margin: 0,
        fontWeight: 'normal',
    },
    highlight: {
        fontWeight: 'bold',
        color: '#00d084',
    },
    statusBadge: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        backgroundColor: '#1b2626',
        color: '#00d084',
        padding: '0.4rem 1rem',
        borderRadius: '20px',
        fontSize: '0.85rem',
        fontWeight: 'bold',
        border: '1px solid #00d08433',
    },
    wsBadge: {
        width: '10px',
        height: '10px',
        borderRadius: '50%',
    },
    badgeText: {
        fontSize: '0.85rem',
        fontWeight: '600',
        color: '#a1a5b7',
    },
    listenBtn: {
        backgroundColor: '#323248',
        color: '#ffffff',
        border: 'none',
        borderRadius: '8px',
        padding: '0.6rem 1.2rem',
        cursor: 'pointer',
        fontWeight: '600',
        transition: 'all 0.2s',
        display: 'flex',
        alignItems: 'center',
    },
    listenBtnDisabled: {
        backgroundColor: '#1e1e2d',
        color: '#555',
        border: 'none',
        borderRadius: '8px',
        padding: '0.6rem 1.2rem',
        cursor: 'not-allowed',
        fontWeight: '600',
        display: 'flex',
        alignItems: 'center',
        opacity: 0.6,
    },
    listenBtnActive: {
        backgroundColor: '#f1416c',
        color: '#ffffff',
        border: 'none',
        padding: '0.6rem 1.2rem',
        borderRadius: '8px',
        fontWeight: 'bold',
        cursor: 'pointer',
        boxShadow: '0 4px 10px rgba(241, 65, 108, 0.3)',
        transition: 'all 0.2s ease',
        display: 'flex',
        alignItems: 'center',
        animation: 'pulse 1.5s infinite',
    },
    statusDot: {
        width: '8px',
        height: '8px',
        backgroundColor: '#00d084',
        borderRadius: '50%',
        boxShadow: '0 0 8px #00d084',
    },
    mainSplitLayout: {
        display: 'flex',
        flex: 1,
        overflow: 'hidden',
        position: 'relative', // Nécessaire pour l'overlay absolu
    },
    leftPanel: {
        flex: 6,
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem',
    },
    divider: {
        width: '2px',
        backgroundColor: '#2b2b40',
        margin: '2rem 0',
        borderRadius: '2px',
    },
    rightPanel: {
        flex: 4,
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem',
        backgroundColor: '#11121c',
    },
    panelHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem',
        paddingBottom: '0.8rem',
        borderBottom: '1px solid #2b2b40',
    },
    badgeInfo: {
        backgroundColor: '#2b2b40',
        color: '#b5b5c3',
        padding: '0.3rem 0.8rem',
        borderRadius: '6px',
        fontSize: '0.8rem',
        fontWeight: '600',
    },
    pdfViewerContainer: {
        flex: 1,
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #474761',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden', // On cache les barres de scroll
        boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
        position: 'relative',
        cursor: 'ns-resize', // Indique qu'on peut scroller verticalement
    },
    pdfCanvas: {
        maxWidth: '100%',
        height: 'auto',
        boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
    },
    pdfBlankState: {
        opacity: 0.8,
        textAlign: 'center',
        color: '#000',
    },
    chatArea: {
        flex: 1,
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        backgroundColor: '#151521',
        borderRadius: '12px',
        border: '1px solid #2b2b40',
        marginBottom: '1rem',
    },
    messageAI: {
        display: 'flex',
        flexDirection: 'column',
        alignSelf: 'flex-start',
        maxWidth: '85%',
    },
    bubbleAI: {
        backgroundColor: '#1e1e2d',
        color: '#ffffff',
        padding: '1rem',
        borderRadius: '0 12px 12px 12px',
        border: '1px solid #323248',
        fontSize: '0.95rem',
        lineHeight: '1.4',
        boxShadow: '0 4px 10px rgba(0,0,0,0.2)',
    },
    messageProf: {
        display: 'flex',
        flexDirection: 'column',
        alignSelf: 'flex-end',
        maxWidth: '85%',
    },
    bubbleProf: {
        backgroundColor: '#00d084',
        color: '#0d0d14',
        padding: '1rem',
        borderRadius: '12px 0 12px 12px',
        fontSize: '0.95rem',
        lineHeight: '1.4',
        fontWeight: '500',
        boxShadow: '0 4px 10px rgba(0,208,132,0.2)',
    },
    inputArea: {
        display: 'flex',
        gap: '0.8rem',
    },
    chatInput: {
        flex: 1,
        backgroundColor: '#1e1e2d',
        border: '1px solid #323248',
        color: '#ffffff',
        padding: '1rem',
        borderRadius: '8px',
        fontSize: '0.95rem',
        outline: 'none',
        transition: 'border-color 0.2s',
    },
    sendBtn: {
        backgroundColor: '#123DDA',
        color: '#ffffff',
        border: 'none',
        padding: '0 1.5rem',
        borderRadius: '8px',
        fontWeight: 'bold',
        cursor: 'pointer',
        transition: 'background-color 0.2s',
    },
    overlay: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(10, 10, 15, 0.95)',
        backdropFilter: 'blur(8px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
    },
    welcomeCard: {
        backgroundColor: '#1e1e2d',
        padding: '3rem',
        borderRadius: '32px',
        border: '1px solid #323248',
        textAlign: 'center',
        maxWidth: '500px',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
    },
    aiIcon: {
        fontSize: '4rem',
        marginBottom: '1.5rem',
    },
    welcomeTitle: {
        fontSize: '1.8rem',
        fontWeight: '800',
        color: '#ffffff',
        marginBottom: '1rem',
    },
    welcomeText: {
        fontSize: '1rem',
        color: '#a1a5b7',
        lineHeight: '1.6',
        marginBottom: '2rem',
    },
    startBtn: {
        backgroundColor: '#00d084',
        color: '#0d0d14',
        padding: '1.2rem 2.5rem',
        borderRadius: '16px',
        fontSize: '1.1rem',
        fontWeight: '800',
        border: 'none',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: '0 10px 20px rgba(0, 208, 132, 0.2)',
    },
    replayBtn: {
        background: 'none',
        border: 'none',
        color: '#00d084',
        cursor: 'pointer',
        fontSize: '0.8rem',
        marginLeft: '10px',
        padding: '2px',
        opacity: 0.6,
        transition: 'opacity 0.2s',
    },
    // --- Styles pour le Clarificateur d'Image ---
    clarifierOverlay: {
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0,0,0,0.85)',
        backdropFilter: 'blur(10px)',
        zIndex: 2000,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
    },
    clarifierContent: {
        backgroundColor: '#1e1e2d',
        borderRadius: '24px',
        padding: '2rem',
        maxWidth: '900px',
        width: '100%',
        border: '1px solid #323248',
        boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
    },
    clarifierHeader: {
        marginBottom: '1.5rem',
        textAlign: 'center',
    },
    clarifierGrid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '1.5rem',
        marginTop: '1.5rem',
    },
    suggestionCard: {
        backgroundColor: '#151521',
        borderRadius: '16px',
        padding: '1rem',
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        border: '2px solid transparent',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.8rem',
    },
    suggestionImage: {
        width: '100%',
        height: '180px',
        objectFit: 'cover',
        borderRadius: '12px',
    },
    largeImageContainer: {
        width: '100%',
        height: '400px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#000',
        borderRadius: '16px',
        overflow: 'hidden',
        marginBottom: '1.5rem',
    },
    largeImage: {
        maxHeight: '100%',
        maxWidth: '100%',
        objectFit: 'contain',
    },
    closePopBtn: {
        padding: '0.8rem 2rem',
        borderRadius: '12px',
        border: 'none',
        backgroundColor: '#f1416c',
        color: '#fff',
        fontWeight: 'bold',
        cursor: 'pointer',
    }
};

export default SuperSession;
