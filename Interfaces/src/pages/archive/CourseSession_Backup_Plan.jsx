import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { apiCall, BASE_URL } from '../services/api';

// URL directe vers le serveur FastAPI (port 5005)
const AI_BASE_URL = 'http://localhost:5005';

const CourseSession = () => {
    const { courseId, docId } = useParams();
    const location = useLocation();
    const navigate = useNavigate();
    const [courseTitle, setCourseTitle] = useState(location.state?.courseTitle || 'Chargement...');
    const roleBufferRef = useRef([]); // Tampon pour lissage du rôle


    const [messages, setMessages] = useState([]);
    const [inputQuery, setInputQuery] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const [isListening, setIsListening] = useState(false);
    const [documentMetadata, setDocumentMetadata] = useState(null);
    const [rotation, setRotation] = useState(0);
    const [isSessionActive, setIsSessionActive] = useState(false);
    const [wsStatus, setWsStatus] = useState('connecting'); // 'connecting' | 'connected' | 'disconnected'
    const [welcomeMessage, setWelcomeMessage] = useState("");
    const [isAIPeaking, setIsAIPeaking] = useState(false); // Nouveau flag
    const [imageSuggestions, setImageSuggestions] = useState(null); // { found_images: [], context_understood: "" }
    const [selectedClarifierImage, setSelectedClarifierImage] = useState(null); // Image URL choisie
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
    const recognitionRef = useRef(null);
    const synthRef = useRef(window.speechSynthesis);
    const currentUtteranceRef = useRef(null);
    const speakTimeoutRef = useRef(null);
    const isSpeakingRef = useRef(false);
    const isInitializingRef = useRef(true);
    const isMountedRef = useRef(true);
    const reconnectTimerRef = useRef(null);
    const speechQueueRef = useRef([]);
    const audioRef = useRef(null);           // Lecteur audio HTML (TTS backend)
    const isProcessingQueueRef = useRef(false); // Verrou anti-double traitement
    // Refs miroirs pour éviter les problèmes de fermeture (closure) dans les callbacks statics
    const isSessionActiveRef = useRef(false);
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
    const highlightsRef = useRef([]);           // Accumulateur de bboxes pour la page actuelle
    const [sttMode, setSttMode] = useState('browser'); // 'browser' | 'whisper'
    const sttWsRef = useRef(null);               // WebSocket pour Whisper STT
    const mediaRecorderRef = useRef(null);       // MediaRecorder pour capture micro

    // --- Projecteur ---
    const projectorWindowRef = useRef(null);
    const projectorChannelRef = useRef(null);
    const [isProjectorOpen, setIsProjectorOpen] = useState(false);

    // Auto-scroll pour le dialogue
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // Synchroniser les refs avec le state (appelé à chaque rendu)
    useEffect(() => { isSessionActiveRef.current = isSessionActive; }, [isSessionActive]);
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

        // Configuration Speech Recognition
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.lang = 'fr-FR';
            recognition.continuous = true; // Permettre une écoute plus longue
            recognition.interimResults = true; // Envoyer les résultats au fur et à mesure

            recognition.onresult = (event) => {
                // SÉCURITÉ ABSOLUE : On ignore TOTALEMENT le micro si l'IA s'active ou si on calibre
                if (isSpeakingRef.current || isCalibratingRef.current || isInitializingRef.current || (synthRef.current && synthRef.current.speaking)) {
                    console.log("🎤 Micro bloqué (IA active, Calibration ou Init)");
                    return;
                }

                const result = event.results[event.results.length - 1];
                const transcript = result[0].transcript;
                if (!transcript.trim()) return;

                if (result.isFinal) {
                    console.log("🎤 Professeur dit (Final) :", transcript);
                    addMessage('prof', transcript);
                    handleVoiceCmdRef.current(transcript, true);
                } else {
                    // Pour le tracking sémantique, on envoie les résultats intermédiaires
                    // mais sans ajouter de bulle dans le chat pour ne pas polluer
                    handleVoiceCmdRef.current(transcript, false);
                }
            };

            recognition.onerror = (event) => {
                console.error("Speech recognition error:", event.error);
                // On ne coupe pas forcément tout sur un simple "no-speech"
                if (event.error === 'no-speech' || event.error === 'aborted') {
                    console.log("🎤 Erreur mineure, on tente de maintenir l'écoute...");
                } else {
                    setIsListening(false);
                }
            };

            recognition.onend = () => {
                // SÉCURITÉ : Si on est censé écouter (Session active OU attente première partie), on relance
                const shouldBeListening = isListeningRef.current || isWaitingForFirstPartRef.current;

                if (shouldBeListening && isMountedRef.current && !isCalibratingRef.current) {
                    console.log("🎤 Reconnaissance terminée mais session/attente active : relance...");
                    try {
                        recognition.start();
                    } catch (e) {
                        console.error("Échec relance micro:", e);
                    }
                } else {
                    setIsListening(false);
                }
            };

            recognitionRef.current = recognition;
        }

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
            if (synthRef.current) synthRef.current.cancel();
            if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
            if (recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch(e) {}
            }
        };
    }, []);

    // Debug voix
    useEffect(() => {
        const checkVoices = () => {
            const v = window.speechSynthesis.getVoices();
            if (v.length > 0) {
                console.log("Voix disponibles :", v.map(i => i.name));
            }
        };
        window.speechSynthesis.onvoiceschanged = checkVoices;
        checkVoices();
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
        const ws = new WebSocket('ws://localhost:8085/ws/navigation');
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
                        speakAndShow(data.text);
                    }

                    if (data.clarification) {
                        console.log("🎨 Suggestions d'images reçues :", data.clarification);
                        setImageSuggestions(data.clarification);
                        setIsClarifierProcessing(false);
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
        speakAndShow(`Écoute active démarrée. Je suis prêt.`);
    };

    const testAudio = () => {
        console.log("🧪 Test audio manuel...");
        speakAndShow("Vérification du système audio. Si vous m'entendez, tout est prêt.", false);
    };

    // --- NOUVEAU : STRATÉGIE ACOUSTIQUE (CALIBRATION) ---
    const startCalibration = async () => {
        setIsCalibrating(true);
        waitingForCalibrationRef.current = true; // On arme le déclencheur pour onSpeechEnd

        // OPTIMISATION LAG : On demande les permissions micro dès maintenant
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            preAuthorizedStreamRef.current = stream;
            console.log("🎤 Flux micro pré-autorisé pendant les instructions.");
        } catch (err) {
            console.warn("⚠️ Impossible de pré-autoriser le micro:", err);
        }

        const introText = "Phase de calibration vocale : Veuillez dire à haute voix : 'Bonjour, pour cette session le nom de l'assistant est', et donnez le nom de l'assistant.";
        speakAndShow(introText);
        console.log("📢 Calibration : Instructions envoyées, attente de onSpeechEnd...");
    };

    const performCalibrationCapture = async () => {
        console.log("🎤 Mode Capture : Démarrage IMMÉDIAT.");
        try {
            // Utiliser le flux pré-autorisé ou en ouvrir un nouveau si besoin
            const stream = preAuthorizedStreamRef.current || await navigator.mediaDevices.getUserMedia({ audio: true });
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioContext.createMediaStreamSource(stream);
            const analyzer = audioContext.createAnalyser();
            analyzer.fftSize = 256;
            source.connect(analyzer);

            const bufferLength = analyzer.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            let capturedName = aiName; // On garde le nom actuel (Siri par défaut) si rien n'est capté

            if (SpeechRecognition) {
                const tempRec = new SpeechRecognition();
                tempRec.lang = 'fr-FR';
                tempRec.continuous = true;
                tempRec.interimResults = true;

                // Stop-words pour éviter les faux positifs comme "De" ou "Et"
                const stopWords = ["de", "et", "le", "la", "l'", "un", "une", "est", "mon", "nom", "pour", "cette", "session", "assistant"];

                tempRec.onresult = (event) => {
                    const lastResultIndex = event.results.length - 1;
                    const transcript = event.results[lastResultIndex][0].transcript.trim().toLowerCase();
                    const isFinal = event.results[lastResultIndex].isFinal;

                    console.log(`🎤 [Calibration] ${isFinal ? 'FINAL' : 'Interim'}: "${transcript}"`);

                    // Logique robuste : On cherche le mot APRÈS le DERNIER mot-clé candidat
                    const keywords = ["assistant est", "nom est", "appelle", "est"];
                    let bestMatch = null;

                    keywords.forEach(kw => {
                        const index = transcript.lastIndexOf(kw);
                        if (index !== -1) {
                            // Extraire la partie après le mot-clé
                            const after = transcript.substring(index + kw.length).trim();
                            const words = after.split(/\s+/);
                            if (words.length > 0 && words[0].length > 1) {
                                // Filtrer si c'est un stop-word
                                if (!stopWords.includes(words[0])) {
                                    bestMatch = words[0];
                                }
                            }
                        }
                    });

                    if (bestMatch) {
                        capturedName = bestMatch.charAt(0).toUpperCase() + bestMatch.slice(1).toLowerCase();
                        console.log("🤖 [Calibration] Nom validé:", capturedName);
                    }
                };
                tempRec.start();
                setTimeout(() => tempRec.stop(), 10000);
            }

            let samples = [];
            let count = 0;
            const interval = setInterval(() => {
                analyzer.getByteFrequencyData(dataArray);
                const avgFreq = dataArray.reduce((a, b) => a + b) / bufferLength;
                samples.push(avgFreq);
                count++;

                if (count > 100) { // 10 secondes
                    clearInterval(interval);
                    const finalProfile = samples.reduce((a, b) => a + b) / samples.length;
                    setProfVoiceProfile(finalProfile);
                    setAiName(capturedName);
                    setIsCalibrating(false);
                    isInitializingRef.current = false;
                    preAuthorizedStreamRef.current = null;

                    addMessage('ai', `Calibration terminée. Votre voix est enregistrée et mon nom est ${capturedName}.`);
                    speakAndShow(`C'est noté. Je m'appelle ${capturedName}. Par quelle partie de votre cours "${courseTitle}" souhaitez-vous commencer ?`);

                    setIsWaitingForFirstPart(true);
                    setTimeout(() => {
                        if (!isListeningRef.current) toggleListening();
                    }, 2000);

                    stream.getTracks().forEach(t => t.stop());
                }
            }, 100);
        } catch (err) {
            console.error("Erreur calibration:", err);
            setIsCalibrating(false);
            isInitializingRef.current = false;
        }
    };

    const analyzeCurrentVoice = () => {
        // [PAUSE] Le basculement automatique est mis en pause jusqu'à nouvel ordre.
        return 'PROFESSOR';
/*
        if (!analyzerRef.current || !profVoiceProfile) return 'PROFESSOR';

        const bufferLength = analyzerRef.current.frequencyBinCount;
...
        const smoothedRole = counts['STUDENT'] >= 4 ? 'STUDENT' : 'PROFESSOR';
        return smoothedRole;
*/
    };

    const initializeSession = async (profId) => {
        try {
            // 0. Récupérer les métadonnées du cours (incluant les documents)
            const courseRes = await apiCall(`/api/courses/${profId}/${courseId}`);
            if (courseRes.success) {
                const courseData = courseRes.data;
                setCourseMetadata(courseData);
                // Fallback robustesse : MongoDB utilise 'nom', mais le frontend cherche 'titre'
                const displayTitle = courseData.titre || courseData.nom || 'Sans titre';
                setCourseTitle(displayTitle);
                
                const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
                const profName = storedUser.fullName || storedUser.email?.split('@')[0] || "Docteur";
                setWelcomeMessage(`Bonjour ${profName}, prêt pour votre cours sur "${displayTitle}" ?`);

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

    const scrollToPage = (num) => {
        // Clear highlights on page change
        highlightsRef.current = [];
        if (overlayCanvasRef.current) {
            const ctx = overlayCanvasRef.current.getContext('2d');
            ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
        }
        renderPage(num);
    };

    // --- Sync page vers la fenêtre projecteur ---
    useEffect(() => {
        if (projectorChannelRef.current) {
            projectorChannelRef.current.postMessage({ type: 'PAGE_CHANGE', page: currentPage });
        }
    }, [currentPage]);

    const openProjector = () => {
        const channel = new BroadcastChannel('pdf_projector_sync');
        projectorChannelRef.current = channel;
        // Dès que la fenêtre projecteur est prête, envoyer la page courante
        channel.onmessage = (e) => {
            if (e.data.type === 'READY') {
                channel.postMessage({ type: 'PAGE_CHANGE', page: currentPageRef.current });
            }
        };
        const win = window.open(
            `/pdf-projector/${docId}`,
            'pdf_projector',
            'width=1280,height=800,menubar=no,toolbar=no,location=no,status=no'
        );
        projectorWindowRef.current = win;
        setIsProjectorOpen(true);
        // Détecter fermeture manuelle de la fenêtre projecteur
        const pollClosed = setInterval(() => {
            if (win && win.closed) {
                clearInterval(pollClosed);
                channel.close();
                projectorWindowRef.current = null;
                projectorChannelRef.current = null;
                setIsProjectorOpen(false);
            }
        }, 1000);
    };

    const closeProjector = () => {
        projectorWindowRef.current?.close();
        projectorChannelRef.current?.close();
        projectorWindowRef.current = null;
        projectorChannelRef.current = null;
        setIsProjectorOpen(false);
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

        // On ajoute la nouvelle bbox à notre accumulateur
        // On évite les doublons d'index si le backend les renvoie (optionnel mais propre)
        highlightsRef.current.push(bbox);

        // On limite l'accumulation pour éviter de saturer (ex: 50 derniers mots) ou on garde tout ?
        // L'utilisateur veut "garder les mots lus", donc on garde tout pour la page.
        
        ctx.clearRect(0, 0, overlay.width, overlay.height);

        highlightsRef.current.forEach((box, idx) => {
            const [x0, y0, x1, y1] = box;
            const [rx0, ry0, rx1, ry1] = viewport.convertToViewportRectangle([x0, y0, x1, y1]);
            
            const rectX = Math.min(rx0, rx1);
            const rectY = Math.min(ry0, ry1);
            const rectW = Math.abs(rx1 - rx0);
            const rectH = Math.abs(ry1 - ry0);

            // Dégradé de couleur : le mot actuel est plus vif, les anciens plus clairs
            const isLatest = idx === highlightsRef.current.length - 1;
            ctx.fillStyle = isLatest ? "rgba(255, 255, 0, 0.45)" : "rgba(255, 255, 0, 0.2)";
            ctx.strokeStyle = isLatest ? "rgba(255, 165, 0, 0.8)" : "rgba(255, 165, 0, 0.3)";
            
            ctx.fillRect(rectX, rectY, rectW, rectH);
            ctx.strokeRect(rectX, rectY, rectW, rectH);
        });

        // Suppression automatique après un long silence (10s) pour ne pas polluer l'écran indéfiniment
        if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
        highlightTimerRef.current = setTimeout(() => {
            highlightsRef.current = [];
            ctx.clearRect(0, 0, overlay.width, overlay.height);
        }, 10000);
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

    // Refs pour la déduplication du TTS
    const lastSpeechTextRef = useRef("");
    const lastSpeechTimeRef = useRef(0);

    const speakAndShow = (text, addMessageFlag = true) => {
        if (!text) return;

        // 1. Déduplication forte : Ignorer si le même texte arrive dans un intervalle de 2s
        // (Augmenté de 800ms à 2000ms car les latences réseau peuvent espacer les doublons)
        const now = Date.now();
        if (text === lastSpeechTextRef.current && (now - lastSpeechTimeRef.current < 2000)) {
            console.log("🚫 Doublon TTS bloqué :", text);
            return;
        }
        lastSpeechTextRef.current = text;
        lastSpeechTimeRef.current = now;

        // 2. Filtrage anti-interruption lors de l'initialisation
        if (text.includes("connecté") && (isInitializingRef.current || isSpeakingRef.current)) {
            console.log("🛡️ Filtre anti-interruption : Message ignoré.");
            return;
        }

        if (addMessageFlag) addMessage('ai', text);
        console.log("📢 Mise en file d'attente :", text);

        speechQueueRef.current.push(text);
        processSpeechQueue();
    };

    // ---------------------------------------------------------------------------
    // 🔊  Système audio double-couche : Backend TTS (OpenAI) + fallback navigateur
    // ---------------------------------------------------------------------------

    /** Lecture de secours avec window.speechSynthesis si le backend n'est pas dispo */
    const fallbackSpeak = (text) => {
        const synth = synthRef.current;
        if (!synth) {
            onSpeechEnd();
            return;
        }
        synth.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'fr-FR';
        const voices = synth.getVoices();
        const bestVoice = voices.find(v => v.lang.includes('fr-FR') && v.localService &&
            (v.name.includes('Thomas') || v.name.includes('Amelie')))
            || voices.find(v => v.lang.includes('fr-FR') && v.localService)
            || voices.find(v => v.lang.startsWith('fr'));
        if (bestVoice) utter.voice = bestVoice;
        utter.volume = 1.0;
        utter.rate = 1.0;

        // Heartbeat anti-blocage macOS Chrome
        const heartbeat = setInterval(() => {
            if (synth.speaking && synth.paused) synth.resume();
        }, 500);

        utter.onstart = () => setIsAIPeaking(true);
        utter.onend = () => { clearInterval(heartbeat); onSpeechEnd(); };
        utter.onerror = (e) => {
            clearInterval(heartbeat);
            if (e.error !== 'interrupted' && e.error !== 'canceled')
                console.error("❌ Fallback TTS erreur :", e.error);
            onSpeechEnd();
        };
        currentUtteranceRef.current = utter;
        synth.speak(utter);
        if (synth.paused) synth.resume();
    };

    /** Appelé quand un message audio se termine (backend ou fallback) */
    const onSpeechEnd = () => {
        if (!isMountedRef.current) return;
        setIsAIPeaking(false);
        isProcessingQueueRef.current = false;
        currentUtteranceRef.current = null;

        // Nettoyage des highlights quand l'IA a fini de parler (nouvelle séquence)
        highlightsRef.current = [];
        if (overlayCanvasRef.current) {
            const ctx = overlayCanvasRef.current.getContext('2d');
            ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
        }

        // GESTION CALIBRATION : Déclenchement IMMÉDIAT (sans attendre l'anti-écho de 1.5s)
        if (waitingForCalibrationRef.current) {
            waitingForCalibrationRef.current = false;
            performCalibrationCapture();
        }

        // Anti-écho (pour la reconnaissance standard) : Porter l'IA à "silencieuse" avec délai
        setTimeout(() => {
            isSpeakingRef.current = false;
            lastSpeechEndTimeRef.current = Date.now();
            console.log("🎤 Micro débloqué (sécurité anti-écho)");
        }, 1500);

        setTimeout(processSpeechQueue, 200);
    };

    /** Traite le prochain élément de la file. Async pour await fetch + Audio.play() */
    const processSpeechQueue = async () => {
        if (isProcessingQueueRef.current) return; // déjà en cours
        if (speechQueueRef.current.length === 0) return;

        const text = speechQueueRef.current.shift();
        isProcessingQueueRef.current = true;
        isSpeakingRef.current = true;

        console.log("🔊 Tentative TTS backend pour :", text.substring(0, 50));

        try {
            const response = await fetch(`${AI_BASE_URL}/api/ai/tts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });

            if (response.ok) {
                const data = await response.json();

                // Si le backend dit "fallback", on utilise le Web Speech API
                if (data.fallback) {
                    console.log("🔄 Backend TTS indisponible — fallback navigateur activé");
                    setIsAIPeaking(true);
                    fallbackSpeak(text);
                    return;
                }

                // Lire l'audio MP3 généré par OpenAI
                const audioUrl = `${AI_BASE_URL}${data.url}`;
                console.log("🎵 Lecture audio OpenAI :", audioUrl);

                const audio = new Audio(audioUrl);
                audioRef.current = audio;

                audio.onplay = () => setIsAIPeaking(true);
                audio.onended = () => {
                    console.log("✅ Audio OpenAI terminé");
                    onSpeechEnd();
                };
                audio.onerror = (e) => {
                    console.error("❌ Erreur lecture audio MP3 :", e);
                    // Fallback si le fichier audio ne peut pas être lu
                    fallbackSpeak(text);
                };

                await audio.play();
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (err) {
            console.warn("⚠️ TTS backend injoignable, fallback navigateur :", err.message);
            setIsAIPeaking(true);
            fallbackSpeak(text);
        }
    };

    const addMessage = (sender, text) => {
        setMessages(prev => [...prev, { id: Date.now() + Math.random(), sender, text }]);
    };

    const toggleListening = async () => {
        if (!recognitionRef.current) {
            alert("La reconnaissance vocale n'est pas supportée sur ce navigateur.");
            return;
        }

        if (isListening) {
            recognitionRef.current.stop();
            if (audioContextRef.current) {
                audioContextRef.current.close();
                audioContextRef.current = null;
            }
            setIsListening(false);
        } else {
            // Initialisation de l'analyseur audio pour le rôle (Acoustic Strategy)
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const source = audioContext.createMediaStreamSource(stream);
                const analyzer = audioContext.createAnalyser();
                analyzer.fftSize = 256;
                source.connect(analyzer);
                audioContextRef.current = audioContext;
                analyzerRef.current = analyzer;
            } catch (e) {
                console.warn("AudioContext non dispo pour la biométrie:", e);
            }

            // Arrêter la voix de l'IA si elle parle
            if (synthRef.current) synthRef.current.cancel();

            recognitionRef.current.start();
            setIsListening(true);
        }
    };

    const handleVoiceCommand = (transcript, isFinal = true) => {
        // Lire les refs (toujours à jour, pas les valeurs de closure)
        // On permet l'écoute si la session est active OU si on attend la première partie après calibration
        if (!isSessionActiveRef.current && !isWaitingForFirstPart) return;

        // Anti-écho supplémentaire : Ignorer les transcripts qui arrivent TROP tôt après la fin de la voix IA (2s)
        const now = Date.now();
        if (now - lastSpeechEndTimeRef.current < 2000) {
            console.log("🤫 Ignoré (Fenêtre de sécurité anti-écho)");
            return;
        }

        // DÉDUPLICATION TRANSCRIPT : Ignorer si exactement le même texte arrive deux fois de suite très vite
        // (Peut arriver avec des instances de reconnaissance fantômes ou des reprises onend agressives)
        // Augmenté à 3 secondes car les logs montrent des écarts importants
        if (isFinal && transcript === lastTranscriptRef.current && (now - lastRequestTimeRef.current < 3000)) {
            console.log("🚫 Doublon de transcript ignoré (Filtre 3s) :", transcript);
            return;
        }

        if (isFinal) {
            console.log("📝 Enregistrement du dernier transcript pour déduplication :", transcript);
            lastTranscriptRef.current = transcript;
            lastRequestTimeRef.current = now;
        }

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
                speakAndShow("C'est fermé.");
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
                        role: role,
                        addressed: addressed // TRÈS IMPORTANT : Dit au serveur que le trigger word a été utilisé
                    }));
                }
            } else if (role === 'PROFESSOR') {
                console.log("🧘 L'IA reste discrète (pas de trigger word)");
            }
        }
    };

    // Ref vers handleVoiceCommand pour que recognition.onresult puisse toujours appeler
    // la version la plus récente (sans problème de closure)
    const handleVoiceCmdRef = useRef(handleVoiceCommand);
    useEffect(() => { handleVoiceCmdRef.current = handleVoiceCommand; });

    // -----------------------------------------------------------------------
    // 🎤 Mode STT alternatif : Whisper local via WebSocket /ws/stt
    // Utilisé si sttMode === 'whisper'. Conserve le Web Speech API par défaut.
    // -----------------------------------------------------------------------
    const startWhisperSTT = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: {
                channelCount: 1,
                sampleRate: 16000
            }});

            // Connexion WebSocket STT
            const wsUrl = `ws://localhost:5005/ws/stt`;
            const ws = new WebSocket(wsUrl);
            sttWsRef.current = ws;

            ws.onopen = () => console.log('🎤 [Whisper WS] Connecté');
            ws.onerror = (e) => console.error('❌ [Whisper WS] Erreur:', e);

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'TRANSCRIPT' && data.text) {
                        // Routage vers le même handleVoiceCommand qu'avec Web Speech API
                        handleVoiceCmdRef.current(data.text, true);
                    }
                } catch(e) { console.warn('[Whisper STT] Parse error', e); }
            };

            // MediaRecorder : capture audio en chunks PCM via AudioContext
            const audioCtx = new AudioContext({ sampleRate: 16000 });
            const source = audioCtx.createMediaStreamSource(stream);
            const processor = audioCtx.createScriptProcessor(4096, 1, 1);

            processor.onaudioprocess = (e) => {
                if (ws.readyState !== WebSocket.OPEN) return;
                const float32 = e.inputBuffer.getChannelData(0);
                // Conversion Float32 -> PCM16
                const pcm16 = new Int16Array(float32.length);
                for (let i = 0; i < float32.length; i++) {
                    pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(float32[i] * 32767)));
                }
                ws.send(pcm16.buffer);
            };

            source.connect(processor);
            processor.connect(audioCtx.destination);
            mediaRecorderRef.current = { stream, audioCtx, processor, source };

            console.log('✅ Whisper STT démarré.');
        } catch (err) {
            console.error('❌ Impossible de démarrer Whisper STT:', err);
            setSttMode('browser'); // Fallback automatique
        }
    };

    const stopWhisperSTT = () => {
        if (mediaRecorderRef.current) {
            const { stream, audioCtx, processor, source } = mediaRecorderRef.current;
            source.disconnect();
            processor.disconnect();
            audioCtx.close();
            stream.getTracks().forEach(t => t.stop());
            mediaRecorderRef.current = null;
        }
        if (sttWsRef.current) {
            // Forcer la transcription du buffer restant
            if (sttWsRef.current.readyState === WebSocket.OPEN) {
                sttWsRef.current.send(JSON.stringify({ command: 'FLUSH' }));
            }
            sttWsRef.current.close();
            sttWsRef.current = null;
        }
        console.log('🛑 Whisper STT arrêté.');
    };

    // Synchronisation démarrage/arrêt selon le mode STT
    useEffect(() => {
        if (sttMode === 'whisper' && isListening) {
            startWhisperSTT();
        } else {
            stopWhisperSTT();
        }
        return () => stopWhisperSTT();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sttMode, isListening]);

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
                speakAndShow("Source ajoutée avec succès.");
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
        setIsClarifierProcessing(true);
        
        try {
            const res = await fetch(`${AI_BASE_URL}/api/ai/explain-selected-image`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_url: imgUrl,
                    student_remark: imageSuggestions?.student_remark || "Question sur cette image",
                    context_analysis: imageSuggestions?.context_understood || ""
                })
            });
            
            if (res.ok) {
                const data = await res.json();
                if (data.explanation) {
                    speakAndShow(data.explanation);
                }
            } else {
                speakAndShow("Désolé, je n'ai pas pu analyser cette image spécifique.");
            }
        } catch (err) {
            console.error("Erreur analyse image sélectionnée:", err);
            speakAndShow("Une erreur est survenue lors de l'analyse.");
        } finally {
            setIsClarifierProcessing(false);
        }
    };

    const handleCloseClarifier = () => {
        setImageSuggestions(null);
        setSelectedClarifierImage(null);
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
                    {profVoiceProfile ? (
                        <div style={{
                            ...styles.badgeInfo,
                            backgroundColor: currentRole === 'PROFESSOR' ? '#00d08422' : '#f1416c22',
                            color: currentRole === 'PROFESSOR' ? '#00d084' : '#f1416c',
                            border: `1px solid ${currentRole === 'PROFESSOR' ? '#00d08444' : '#f1416c44'}`
                        }}>
                            Role: {currentRole}
                        </div>
                    ) : (
                        <button onClick={startCalibration} style={styles.rotateBtn}>
                            🎙️ Calibrer ma voix
                        </button>
                    )}
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
                            {!isProjectorOpen ? (
                                <button
                                    onClick={openProjector}
                                    disabled={!documentMetadata}
                                    title="Afficher le PDF sur le projecteur"
                                    style={{
                                        ...styles.rotateBtn,
                                        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                        color: '#fff',
                                        border: 'none',
                                        opacity: documentMetadata ? 1 : 0.4,
                                        cursor: documentMetadata ? 'pointer' : 'not-allowed',
                                    }}
                                >
                                    📽️ Projecteur
                                </button>
                            ) : (
                                <button
                                    onClick={closeProjector}
                                    title="Fermer la fenêtre projecteur"
                                    style={{
                                        ...styles.rotateBtn,
                                        background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                        color: '#fff',
                                        border: 'none',
                                        cursor: 'pointer',
                                    }}
                                >
                                    ✖ Fermer Projecteur
                                </button>
                            )}
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
                                        zIndex: 10,
                                        pointerEvents: 'none',
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
                            {imageSuggestions.found_images && imageSuggestions.found_images.length > 0 ? (
                                imageSuggestions.found_images.map((imgUrl, idx) => (
                                    <div 
                                        key={idx} 
                                        style={styles.suggestionCard} 
                                        onClick={() => handleSelectImage(imgUrl)}
                                        onMouseEnter={(e) => e.currentTarget.style.borderColor = '#00d084'}
                                        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'transparent'}
                                    >
                                        <img 
                                            src={`${AI_BASE_URL}/api/ai/proxy-image?url=${encodeURIComponent(imgUrl)}`} 
                                            alt={`Sugg ${idx}`} 
                                            style={styles.suggestionImage} 
                                            onError={(e) => { 
                                                console.warn("Proxy failure, trying direct URL:", imgUrl);
                                                e.target.src = imgUrl; 
                                            }}
                                        />
                                        <div style={{ textAlign: 'center', color: '#00d084', fontSize: '0.8rem', fontWeight: '600', padding: '5px' }}>
                                            Image alternative {idx + 1}
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div style={{ gridColumn: '1 / span 3', textAlign: 'center', padding: '2rem', color: '#b5b5c3' }}>
                                    <i className="fa-solid fa-image-slash" style={{ fontSize: '3rem', marginBottom: '1rem', display: 'block', opacity: 0.5 }}></i>
                                    <p>Aucune image alternative trouvée pour ce concept.</p>
                                    <p style={{ fontSize: '0.8rem' }}>Requête : {imageSuggestions.search_query || "N/A"}</p>
                                </div>
                            )}
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
                            <img src={`${AI_BASE_URL}/api/ai/proxy-image?url=${encodeURIComponent(selectedClarifierImage)}`} style={styles.largeImage} alt="Clarification" />
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <h3 style={{ color: '#00d084', marginBottom: '1rem' }}>
                                {isClarifierProcessing ? "Analyse de l'image en cours..." : "Explication sur-mesure"}
                            </h3>
                            <div style={{ 
                                color: '#b5b5c3', 
                                marginBottom: '2rem', 
                                maxHeight: '200px', 
                                overflowY: 'auto',
                                padding: '1rem',
                                backgroundColor: '#151521',
                                borderRadius: '12px',
                                textAlign: 'left',
                                fontSize: '0.9rem',
                                border: '1px solid #323248'
                            }}>
                                {isClarifierProcessing ? (
                                    <div style={{ textAlign: 'center', padding: '1rem' }}>
                                        <i className="fa-solid fa-circle-notch fa-spin" style={{ fontSize: '2rem', color: '#00d084' }}></i>
                                    </div>
                                ) : (
                                    messages.filter(m => m.sender === 'ai').slice(-1)[0]?.text || "L'assistant analyse l'image..."
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
    rotateBtn: {
        backgroundColor: '#2b2b40',
        color: '#e4e6ef',
        border: '1px solid #474761',
        padding: '0.3rem 0.8rem',
        borderRadius: '6px',
        fontSize: '0.8rem',
        cursor: 'pointer',
        transition: 'all 0.2s',
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

export default CourseSession;
