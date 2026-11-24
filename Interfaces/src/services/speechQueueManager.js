let queue = [];
let isProcessing = false;

/**
 * Gère une file d'attente pour la synthèse vocale (TTS)
 */
export const enqueueSpeech = async (text, options = {}) => {
    if (!text) return;
    queue.push({ text, options });
    if (!isProcessing) {
        processQueue();
    }
};

export const clearSpeechQueue = () => {
    queue = [];
    isProcessing = false;
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
};

const processQueue = async () => {
    if (queue.length === 0) {
        isProcessing = false;
        return;
    }

    isProcessing = true;
    const { text, options } = queue.shift();

    try {
        if (options.setIsAIPeaking) options.setIsAIPeaking(true);
        if (options.onSpeechStart) options.onSpeechStart();

        console.log(`🔊 Lecture TTS: "${text.substring(0, 50)}..."`);

        // Tentative d'appel au backend pour le TTS OpenAI
        const response = await fetch(`${options.backendUrl}/api/ai/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        if (response.ok) {
            const data = await response.json();
            
            if (data.url) {
                const audio = new Audio(`${options.backendUrl}${data.url}`);
                await new Promise((resolve, reject) => {
                    audio.onended = resolve;
                    audio.onerror = reject;
                    audio.play().catch(reject);
                });
            } else if (data.fallback && options.fallbackSpeak) {
                options.fallbackSpeak(text);
                // On attend un peu que le synthétiseur commence
                await new Promise(r => setTimeout(r, 1000));
            }
        } else if (options.fallbackSpeak) {
            options.fallbackSpeak(text);
        }
    } catch (error) {
        console.error("Erreur dans speechQueueManager:", error);
        if (options.fallbackSpeak) options.fallbackSpeak(text);
    } finally {
        if (options.setIsAIPeaking) options.setIsAIPeaking(false);
        if (options.onSpeechEnd) options.onSpeechEnd();
        
        // Petite pause entre deux messages
        setTimeout(processQueue, 300);
    }
};
