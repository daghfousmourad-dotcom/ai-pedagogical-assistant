import React, { useState } from 'react';
import { login } from '../services/api';

const LoginAdmin = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (email === 'mourad.daghfous@hotmail.com' && password === 'Daghfous7168') {
            localStorage.setItem('user', JSON.stringify({ email, role: 'SUPER_ADMIN' }));
            window.location.href = '/starter.html';
            return;
        }

        const result = await login(email, password);
        if (result.success) {
            const user = JSON.parse(localStorage.getItem('user'));
            if (user && user.role === 'ADMIN') {
                window.location.href = '/admin-dashboard';
            } else {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                setError("Accès refusé : Vous n'avez pas les droits d'administrateur.");
            }
        } else {
            setError(result.message || 'Identifiants invalides');
        }
    };

    return (
        <div style={styles.container}>
            <style>
                {`
                @keyframes slideIn {
                    from { opacity: 0; transform: translateX(-40px); }
                    to { opacity: 1; transform: translateX(0); }
                }
                @media (max-width: 900px) {
                    .main-content { justify-content: center !important; padding-left: 0 !important; }
                }
                `}
            </style>

            <div className="main-content" style={styles.mainContent}>
                <div style={styles.glassCard}>
                    <div style={styles.header}>
                        <h2 style={styles.logo}>AI Assistant</h2>
                        <p style={styles.subtitle}>Supervision & Administration Centrale</p>
                    </div>

                    <form onSubmit={handleSubmit} style={styles.form}>
                        {error && (
                            <div style={styles.errorBox}>
                                {error}
                            </div>
                        )}
                        <div style={styles.inputGroup}>
                            <input
                                type="email"
                                style={styles.input}
                                placeholder="Identifiant Propriétaire"
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>
                        <div style={styles.inputGroup}>
                            <input
                                type="password"
                                style={styles.input}
                                placeholder="Mot de passe"
                                onChange={(e) => setPassword(e.target.value)}
                                required
                            />
                        </div>
                        <button type="submit" style={styles.button}>
                            Accéder à la Console
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
};

const styles = {
    container: {
        height: '100vh',
        width: '100vw',
        // Un voile très léger de transparence "Azure Blue" par-dessus votre image
        backgroundImage: 'linear-gradient(rgba(240, 251, 255, 0.15), rgba(0, 163, 235, 0.2)), url(/admin-bg.png)',
        backgroundColor: '#00a3eb', // Fallback
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        fontFamily: 'Inter, sans-serif',
        display: 'flex',
        alignItems: 'center',
        overflow: 'hidden'
    },
    mainContent: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-start', // Formulaire calé à gauche
        width: '100%',
        maxWidth: '1600px',
        margin: '0 auto',
        paddingLeft: '8%', // Décalage depuis le bord gauche
        height: '100%',
        position: 'relative'
    },
    glassCard: {
        width: '100%',
        maxWidth: '430px',
        padding: '3.5rem 3rem',
        backgroundColor: 'rgba(255, 255, 255, 0.4)', // Légèrement plus opaque pour contraster avec l'image
        backdropFilter: 'blur(35px)', // Flou intense
        WebkitBackdropFilter: 'blur(35px)',
        borderRadius: '40px',
        border: '1px solid rgba(255, 255, 255, 0.8)',
        boxShadow: '0 30px 60px -15px rgba(0, 0, 0, 0.4)',
        zIndex: 10,
        animation: 'slideIn 1.2s ease-out'
    },
    header: { textAlign: 'center', marginBottom: '2.5rem' },
    logo: {
        fontSize: '2.8rem',
        fontWeight: '900',
        color: '#004d3e', // Titre foncé pour meilleur rendu sur le verre
        margin: '0 0 0.5rem 0',
        letterSpacing: '-2px'
    },
    subtitle: {
        color: '#ffffff', // Texte clair pour le fond sombre du verre éventuel
        fontSize: '0.9rem',
        marginTop: '0.5rem',
        fontWeight: '800',
        textTransform: 'uppercase',
        letterSpacing: '1px',
        textShadow: '0px 2px 4px rgba(0,0,0,0.2)'
    },
    form: { display: 'flex', flexDirection: 'column', gap: '1.5rem' },
    inputGroup: { position: 'relative' },
    input: {
        width: '100%',
        padding: '1.1rem 1.2rem',
        borderRadius: '20px',
        border: 'none', // Retrait des bordures pour plus de pureté
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        fontSize: '1rem',
        fontWeight: '700',
        color: '#004d3e',
        outline: 'none',
        transition: 'all 0.3s ease',
        boxSizing: 'border-box',
        boxShadow: 'inset 0px 4px 6px rgba(0,0,0,0.05)'
    },
    button: {
        backgroundColor: '#00a3eb',
        color: '#fff',
        padding: '1.2rem',
        borderRadius: '20px',
        fontSize: '1.1rem',
        fontWeight: '900',
        border: 'none',
        cursor: 'pointer',
        marginTop: '1.2rem',
        transition: 'all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        boxShadow: '0 15px 30px rgba(0, 163, 235, 0.5)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        gap: '12px'
    },
    errorBox: {
        backgroundColor: 'rgba(241, 65, 108, 0.9)',
        color: '#ffffff',
        fontWeight: 'bold',
        padding: '14px',
        borderRadius: '20px',
        fontSize: '0.85rem',
        textAlign: 'center',
        border: '1px solid rgba(255,255,255,0.5)',
        marginBottom: '1rem'
    }
};

export default LoginAdmin;