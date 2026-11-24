import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { BASE_URL } from '../services/api';

const CHANNEL_NAME = 'pdf_projector_sync';

export default function PDFProjectorView() {
    const { docId } = useParams();
    const canvasRef = useRef(null);
    const overlayCanvasRef = useRef(null);
    const pdfDocRef = useRef(null);
    const isRenderingRef = useRef(false);
    const channelRef = useRef(null);
    const lastViewportRef = useRef(null);
    const lastScrollTimeRef = useRef(0);
    const currentPageRef = useRef(null);
    const currentHighlightsRef = useRef([]);
    const [currentPage, setCurrentPage] = useState(null);
    const [totalPages, setTotalPages] = useState(null);
    const [status, setStatus] = useState('Chargement du document...');
    const [clarificationModal, setClarificationModal] = useState(null);

    const renderPage = async (num) => {
        if (!pdfDocRef.current || !canvasRef.current) return;
        if (isRenderingRef.current) return;
        isRenderingRef.current = true;

        try {
            const safeNum = Math.max(1, Math.min(num, pdfDocRef.current.numPages));
            const page = await pdfDocRef.current.getPage(safeNum);

            const canvas = canvasRef.current;
            const ctx = canvas.getContext('2d');

            // Scale to fill the viewport (minus margins)
            const margin = 3;
            const availW = window.innerWidth - margin * 2;
            const availH = window.innerHeight - margin * 2;
            const nativeVp = page.getViewport({ scale: 1 });
            const scale = Math.min(availW / nativeVp.width, availH / nativeVp.height);
            const viewport = page.getViewport({ scale });
            lastViewportRef.current = viewport;

            canvas.width = viewport.width;
            canvas.height = viewport.height;
            
            if (overlayCanvasRef.current) {
                overlayCanvasRef.current.width = viewport.width;
                overlayCanvasRef.current.height = viewport.height;
                const overlayCtx = overlayCanvasRef.current.getContext('2d');
                overlayCtx.clearRect(0, 0, viewport.width, viewport.height);
            }
            currentHighlightsRef.current = [];

            await page.render({ canvasContext: ctx, viewport }).promise;
            
            setCurrentPage(safeNum);
            currentPageRef.current = safeNum;
        } catch (err) {
            console.error('Erreur rendu projecteur:', err);
        } finally {
            isRenderingRef.current = false;
        }
    };

    const drawHighlight = (bbox) => {
        if (!overlayCanvasRef.current || !canvasRef.current || !lastViewportRef.current) return;
        const overlay = overlayCanvasRef.current;
        const viewport = lastViewportRef.current;
        const ctx = overlay.getContext('2d');

        currentHighlightsRef.current.push(bbox);
        ctx.clearRect(0, 0, overlay.width, overlay.height);

        currentHighlightsRef.current.forEach((box, idx) => {
            const [x0, y0, x1, y1] = box;
            const [rx0, ry0, rx1, ry1] = viewport.convertToViewportRectangle([x0, y0, x1, y1]);
            
            const rectX = Math.min(rx0, rx1);
            const rectY = Math.min(ry0, ry1);
            const rectW = Math.abs(rx1 - rx0);
            const rectH = Math.abs(ry1 - ry0);

            const isLatest = idx === currentHighlightsRef.current.length - 1;
            ctx.fillStyle = isLatest ? "rgba(255, 255, 0, 0.45)" : "rgba(255, 255, 0, 0.2)";
            ctx.strokeStyle = isLatest ? "rgba(255, 165, 0, 0.8)" : "rgba(255, 165, 0, 0.3)";
            
            ctx.fillRect(rectX, rectY, rectW, rectH);
            ctx.strokeRect(rectX, rectY, rectW, rectH);
        });
    };

    const handleWheel = (e) => {
        const now = Date.now();
        if (now - lastScrollTimeRef.current < 450) return;

        let newPage = null;
        if (e.deltaY > 40) {
            if (currentPageRef.current < pdfDocRef.current?.numPages) {
                newPage = currentPageRef.current + 1;
            }
        } else if (e.deltaY < -40) {
            if (currentPageRef.current > 1) {
                newPage = currentPageRef.current - 1;
            }
        }

        if (newPage) {
            lastScrollTimeRef.current = now;
            renderPage(newPage);
            // Notifier le maître pour la synchronisation inverse
            if (channelRef.current) {
                try {
                    channelRef.current.postMessage({ type: 'PAGE_CMD', page: newPage });
                } catch (e) {
                    console.warn("⚠️ Impossible de notifier le maître (canal fermé):", e.message);
                }
            }
        }
    };

    useEffect(() => {
        if (!docId) return;

        // Open BroadcastChannel to receive page sync messages
        const channel = new BroadcastChannel(CHANNEL_NAME);
        channelRef.current = channel;

        channel.onmessage = (e) => {
            if (e.data.type === 'PAGE_CHANGE') {
                renderPage(e.data.page);
            } else if (e.data.type === 'HIGHLIGHT') {
                drawHighlight(e.data.bbox);
            } else if (e.data.type === 'CLEAR_HIGHLIGHTS') {
                currentHighlightsRef.current = [];
                if (overlayCanvasRef.current) {
                    const ctx = overlayCanvasRef.current.getContext('2d');
                    ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
                }
            } else if (e.data.type === 'CLARIFICATION_SHOW') {
                setClarificationModal({
                    image_url: e.data.image_url,
                    explanation: e.data.explanation,
                    concept: e.data.concept
                });
            } else if (e.data.type === 'CLARIFICATION_HIDE') {
                setClarificationModal(null);
            }
        };

        // Load PDF
        const token = localStorage.getItem('token');
        const pdfUrl = `${BASE_URL}/api/livesession/documents/${docId}/stream`;

        const loadPdf = async () => {
            try {
                const loadingTask = window.pdfjsLib.getDocument({
                    url: pdfUrl,
                    httpHeaders: { Authorization: `Bearer ${token}` },
                });
                const pdfDoc = await loadingTask.promise;
                pdfDocRef.current = pdfDoc;
                setTotalPages(pdfDoc.numPages);
                setStatus('');

                // Signal the main window that we are ready
                if (channelRef.current) {
                    try {
                        channel.postMessage({ type: 'READY' });
                    } catch (e) {
                        console.warn("⚠️ Canal fermé lors du 'READY'");
                    }
                }
            } catch (err) {
                console.error('Erreur chargement PDF projecteur:', err);
                setStatus('Erreur de chargement du document.');
            }
        };

        loadPdf();

        // Demande de synchronisation immédiate au démarrage
        const syncInterval = setInterval(() => {
            if (channelRef.current && currentPageRef.current === null) {
                console.log("🔄 Tentative de synchronisation initiale...");
                try {
                    channelRef.current.postMessage({ type: 'REQUEST_SYNC' });
                } catch (e) {
                    console.warn("⚠️ Échec postMessage syncInterval");
                }
            } else {
                console.log("✅ Synchronisation réussie, arrêt de l'intervalle.");
                clearInterval(syncInterval);
            }
        }, 1000);

        // Resize: re-render current page when window is resized
        const handleResize = () => {
            if (pdfDocRef.current && canvasRef.current) {
                renderPage(currentPageRef.current || 1);
            }
        };
        window.addEventListener('resize', handleResize);

        return () => {
            clearInterval(syncInterval);
            if (channel) {
                channel.close();
                channelRef.current = null;
            }
            window.removeEventListener('resize', handleResize);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [docId]);

    return (
        <div style={styles.root}>
            {status && (
                <div style={styles.statusOverlay}>
                    <div style={styles.statusCard}>
                        <div style={styles.spinner} />
                        <p style={styles.statusText}>{status}</p>
                    </div>
                </div>
            )}

            {/* PDF Canvas */}
            <div style={styles.canvasWrapper} onWheel={handleWheel}>
                <div style={{ position: 'relative', display: 'inline-block', cursor: 'ns-resize' }}>
                    <canvas ref={canvasRef} style={styles.canvas} />
                    <canvas
                        ref={overlayCanvasRef}
                        style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            zIndex: 10,
                            pointerEvents: 'none',
                        }}
                    />
                    
                    {/* Zones de clic invisibles ou boutons de navigation */}
                    <div 
                        onClick={() => {
                            const newPage = Math.max(1, (currentPage || 1) - 1);
                            renderPage(newPage);
                            channelRef.current?.postMessage({ type: 'PAGE_CMD', page: newPage });
                        }}
                        style={{...styles.navZone, left: 0}} 
                        title="Page Précédente"
                    />
                    <div 
                        onClick={() => {
                            const newPage = Math.min(totalPages || 1, (currentPage || 1) + 1);
                            renderPage(newPage);
                            channelRef.current?.postMessage({ type: 'PAGE_CMD', page: newPage });
                        }}
                        style={{...styles.navZone, right: 0}} 
                        title="Page Suivante"
                    />
                </div>
            </div>

            {/* Minimal HUD: page indicator */}
            {currentPage && totalPages && (
                <div style={styles.hud}>
                    Page {currentPage} / {totalPages}
                </div>
            )}

            {/* Modal de Clarification Visuelle Validée par le Professeur */}
            {clarificationModal && (
                <div style={styles.clarifierOverlay}>
                    <div style={styles.clarifierContent}>
                        <div style={styles.clarifierHeader}>
                            <span style={styles.clarifierBadge}>🎨 Zoom Pédagogique Validé</span>
                            <h2 style={styles.clarifierTitle}>
                                {clarificationModal.concept || "Clarification visuelle du cours"}
                            </h2>
                        </div>
                        <div style={styles.clarifierBody}>
                            <div style={styles.clarifierImageWrapper}>
                                <img 
                                    src={clarificationModal.image_url} 
                                    alt="Clarification" 
                                    style={styles.clarifierImage} 
                                />
                            </div>
                            <div style={styles.clarifierExplanation}>
                                <h3 style={styles.clarifierSubtitle}>💡 Explication du concept :</h3>
                                <p style={styles.clarifierText}>{clarificationModal.explanation}</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

const styles = {
    root: {
        width: '100vw',
        height: '100vh',
        margin: 0,
        padding: '3px',
        backgroundColor: '#002e26', // Dark Teal branded background
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxSizing: 'border-box',
        overflow: 'hidden',
    },
    canvasWrapper: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
    },
    canvas: {
        display: 'block',
        boxShadow: '0 0 30px rgba(255,255,255,0.05)',
        transition: 'opacity 0.25s ease-in-out',
    },
    hud: {
        position: 'fixed',
        bottom: '10px',
        right: '14px',
        backgroundColor: 'rgba(217, 237, 223, 0.15)', // Tinted HUD
        color: '#92b56e',
        fontSize: '0.75rem',
        fontFamily: 'monospace',
        padding: '3px 8px',
        borderRadius: '6px',
        pointerEvents: 'none',
    },
    statusOverlay: {
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#002e26',
        zIndex: 9999,
    },
    statusCard: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '1rem',
    },
    spinner: {
        width: '36px',
        height: '36px',
        border: '3px solid rgba(146, 181, 110, 0.2)',
        borderTop: '3px solid #00885d',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
    },
    statusText: {
        color: '#92b56e',
        fontSize: '0.9rem',
        fontFamily: 'sans-serif',
    },
    navZone: {
        position: 'absolute',
        top: 0,
        bottom: 0,
        width: '15%',
        cursor: 'pointer',
        zIndex: 20,
        backgroundColor: 'rgba(0,0,0,0)', // Invisible
        transition: 'background-color 0.2s',
    },
    clarifierOverlay: {
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(5, 18, 14, 0.92)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 99999,
        padding: '2rem',
        backdropFilter: 'blur(8px)',
        animation: 'fadeIn 0.3s ease-out',
    },
    clarifierContent: {
        backgroundColor: '#0a352a',
        border: '2px solid #00d084',
        borderRadius: '16px',
        maxWidth: '1100px',
        width: '95%',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
        overflow: 'hidden',
    },
    clarifierHeader: {
        padding: '1.2rem 2rem',
        borderBottom: '1px solid rgba(0, 208, 132, 0.2)',
        backgroundColor: '#0d4033',
    },
    clarifierBadge: {
        display: 'inline-block',
        backgroundColor: '#00d084',
        color: '#002e26',
        fontWeight: 'bold',
        fontSize: '0.85rem',
        padding: '4px 10px',
        borderRadius: '20px',
        marginBottom: '0.4rem',
    },
    clarifierTitle: {
        fontSize: '1.5rem',
        fontWeight: '700',
        color: '#ffffff',
        margin: 0,
    },
    clarifierBody: {
        display: 'flex',
        flexDirection: 'row',
        padding: '2rem',
        gap: '2rem',
        alignItems: 'center',
        overflowY: 'auto',
    },
    clarifierImageWrapper: {
        flex: 1,
        maxHeight: '55vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#051b14',
        borderRadius: '12px',
        padding: '1rem',
        border: '1px solid rgba(255,255,255,0.1)',
    },
    clarifierImage: {
        maxWidth: '100%',
        maxHeight: '50vh',
        objectFit: 'contain',
        borderRadius: '8px',
    },
    clarifierExplanation: {
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    clarifierSubtitle: {
        color: '#00d084',
        fontSize: '1.2rem',
        fontWeight: '600',
        margin: 0,
    },
    clarifierText: {
        color: '#d9eddf',
        fontSize: '1.15rem',
        lineHeight: '1.6',
        margin: 0,
        backgroundColor: '#06241b',
        padding: '1.5rem',
        borderRadius: '12px',
        border: '1px solid rgba(0, 208, 132, 0.25)',
    },
};
