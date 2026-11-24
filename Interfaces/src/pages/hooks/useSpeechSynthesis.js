import { useState, useCallback } from 'react';
import { enqueueSpeech, clearSpeechQueue } from '../../services/speechQueueManager';
import { fallbackSpeak } from '../../utils/transcriptFilter';

const AI_BASE_URL = 'http://127.0.0.1:5005';

/**
 * Hook pour gérer la synthèse vocale
 */
export const useSpeechSynthesis = () => {
    const [isAIPeaking, setIsAIPeaking] = useState(false);

    const speak = useCallback((text, options = {}) => {
        if (!text) return;
        
        const speechOptions = {
            backendUrl: AI_BASE_URL,
            fallbackSpeak: fallbackSpeak,
            setIsAIPeaking: setIsAIPeaking,
            onSpeechStart: options.onSpeechStart,
            onSpeechEnd: options.onSpeechEnd
        };

        enqueueSpeech(text, speechOptions);
    }, []);

    const cancelSpeech = useCallback(() => {
        clearSpeechQueue();
        setIsAIPeaking(false);
    }, []);

    return { speak, isAIPeaking, cancelSpeech };
};

export default useSpeechSynthesis;
