/**
 * Utilitaires pour filtrer la transcription et gérer les fallbacks
 */
export const fallbackSpeak = (text) => {
    if (!window.speechSynthesis) return;
    
    // Annuler toute lecture en cours
    window.speechSynthesis.cancel();
    
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'fr-FR';
    
    // Essayer de trouver une voix française naturelle
    const voices = window.speechSynthesis.getVoices();
    const frenchVoice = voices.find(v => v.lang.includes('fr-FR')) || voices.find(v => v.lang.startsWith('fr'));
    if (frenchVoice) utter.voice = frenchVoice;
    
    utter.rate = 1.0;
    utter.pitch = 1.0;
    
    window.speechSynthesis.speak(utter);
};
