import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Hook pour gérer la reconnaissance vocale
 */
export const useSpeechRecognition = () => {
    const [transcript, setTranscript] = useState('');
    const [isListening, setIsListening] = useState(false);
    const recognitionRef = useRef(null);
    const isListeningRef = useRef(false);

    useEffect(() => {
        isListeningRef.current = isListening;
    }, [isListening]);

    useEffect(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            console.error("Speech Recognition API not supported");
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.lang = 'fr-FR';
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event) => {
            let sessionTranscript = '';
            for (let i = 0; i < event.results.length; ++i) {
                sessionTranscript += event.results[i][0].transcript;
            }
            setTranscript(sessionTranscript);
        };

        recognition.onend = () => {
            if (isListeningRef.current) {
                try {
                    // Start a new session without resetting the global state if needed
                    // But here transcript is just the current session.
                    recognition.start();
                } catch (e) {
                    console.error("Error restarting recognition:", e);
                }
            }
        };

        recognitionRef.current = recognition;

        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
        };
    }, []);

    const startListening = useCallback(() => {
        setIsListening(true);
        setTranscript('');
        if (recognitionRef.current) {
            try {
                recognitionRef.current.start();
            } catch (e) {
                console.error("Start listening error:", e);
            }
        }
    }, []);

    const stopListening = useCallback(() => {
        setIsListening(false);
        if (recognitionRef.current) {
            try {
                recognitionRef.current.stop();
            } catch (e) {
                console.error("Stop listening error:", e);
            }
        }
    }, []);

    const resetTranscript = useCallback(() => {
        setTranscript('');
    }, []);

    return { transcript, isListening, startListening, stopListening, resetTranscript };
};

export default useSpeechRecognition;
