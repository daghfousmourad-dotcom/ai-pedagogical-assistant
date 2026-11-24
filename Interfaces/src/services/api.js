export const BASE_URL = 'http://localhost:8080'; // L'adresse de ta Gateway (harmonisé sur localhost)

export const login = async (email, password) => {
    try {
        const response = await fetch(`${BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        const token = await response.text();

        if (response.ok) {
            localStorage.setItem('token', token);
            try {
                // Décodage de la partie payload du JWT (base64)
                const payload = JSON.parse(atob(token.split('.')[1]));
                const userData = {
                    email: payload.sub,
                    role: payload.role,
                    id: payload.id
                };
                localStorage.setItem('user', JSON.stringify(userData));
            } catch (e) {
                localStorage.setItem('user', JSON.stringify({ email }));
            }
            return { success: true };
        } else {
            return { success: false, message: "Identifiants invalides" };
        }
        // eslint-disable-next-line no-unused-vars
    } catch (error) {
        return { success: false, message: "Serveur injoignable" };
    }
};

export const apiCall = async (endpoint, method = 'GET', body = null) => {
    const token = localStorage.getItem('token'); // On récupère le badge du Gardien

    const headers = {
        'Content-Type': 'application/json',
    };

    // Si on a un token, on l'ajoute dans le header Authorization
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
            method,
            headers,
            body: body ? JSON.stringify(body) : null,
        });

        // Si le token est expiré ou invalide (401), on redirige vers login
        if (response.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }

        return await response.json();
    } catch (error) {
        console.error("Erreur API:", error);
        throw error;
    }
};