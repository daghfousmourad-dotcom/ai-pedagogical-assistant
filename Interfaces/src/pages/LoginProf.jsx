import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../services/api';

const LoginProf = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const result = await login(email, password);
            if (result.success) {
                const user = JSON.parse(localStorage.getItem('user'));
                if (user.role === 'ADMIN') {
                    navigate('/admin-dashboard');
                } else {
                    navigate('/dashboard');
                }
            } else {
                setError(result.message);
            }
        } catch (err) {
            setError("Erreur de connexion au serveur");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={styles.container}>
            <style>
                {`
                @keyframes float {
                    0% { transform: translateY(0px); }
                    50% { transform: translateY(-20px); }
                    100% { transform: translateY(0px); }
                }
                @keyframes slideIn {
                    from { opacity: 0; transform: translateX(-40px); }
                    to { opacity: 1; transform: translateX(0); }
                }
                @media (max-width: 900px) {
                    .hero-section { display: none !important; }
                    .main-content { justify-content: center !important; }
                }
                `}
            </style>

            <div className="main-content" style={styles.mainContent}>
                <div className="hero-section" style={styles.heroSection}>
                    <img 
                        src="/hero-cutout-perfect.png" 
                        alt="Student" 
                        style={styles.heroImage} 
                    />
                </div>

                <div style={styles.loginBox}>
                    <h1 style={styles.title}>AI Assistant</h1>
                    <h2 style={styles.subtitle}>Portail Éducatif Intelligent</h2>

                    {error && <div style={styles.error}>{error}</div>}

                <form onSubmit={handleSubmit} style={styles.form}>
                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Adresse Email</label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            style={styles.input}
                            placeholder="nom@etablissement.tn"
                            required
                        />
                    </div>

                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Mot de passe</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            style={styles.input}
                            placeholder="••••••••"
                            required
                        />
                    </div>

                    <button type="submit" style={styles.button} disabled={loading}>
                        {loading ? 'Authentification...' : 'Accéder à mon espace'}
                        {!loading && <span style={{fontSize: '1.2rem'}}>→</span>}
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
        backgroundColor: '#00715d',
        background: 'radial-gradient(circle at 15% 15%, #f7df9f 0%, #92b56e 50%, #00715d 100%)',
        fontFamily: 'Inter, sans-serif',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden'
    },
    mainContent: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center', // Centre le contenu (le formulaire)
        width: '100%',
        maxWidth: '1400px',
        height: '100%',
        position: 'relative' // Nécessaire pour le positionnement de l'heroSection
    },
    heroSection: {
        position: 'absolute',
        left: '2rem', // Pousse l'image à l'extrême gauche
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        animation: 'slideIn 1.5s ease-out, float 8s ease-in-out infinite',
        zIndex: 1
    },
    heroImage: {
        maxWidth: '130%',
        height: 'auto',
        maxHeight: '95vh',
        filter: 'drop-shadow(0 40px 80px rgba(0,0,0,0.3))',
        transform: 'scale(1.1)',
        opacity: 0.95
    },
    loginBox: {
        backgroundColor: 'rgba(217, 237, 223, 0.85)',
        padding: '3.5rem 3rem',
        borderRadius: '40px',
        boxShadow: '0 40px 100px -20px rgba(0, 71, 93, 0.5)',
        width: '100%',
        maxWidth: '430px',
        display: 'flex',
        flexDirection: 'column',
        backdropFilter: 'blur(30px)',
        border: '1px solid rgba(255, 255, 255, 0.4)',
        animation: 'slideIn 1s ease-out',
        zIndex: 10, // Reste au-dessus de tout
        position: 'relative'
    },
    title: {
        color: '#00715d',
        fontSize: '2.8rem',
        fontWeight: '900',
        textAlign: 'center',
        margin: '0 0 0.5rem 0',
        letterSpacing: '-2px'
    },
    subtitle: {
        color: '#599f62',
        fontSize: '1rem',
        textAlign: 'center',
        margin: '0 0 2.5rem 0',
        fontWeight: '600',
        textTransform: 'uppercase',
        letterSpacing: '2px'
    },
    error: {
        backgroundColor: 'rgba(241, 65, 108, 0.1)',
        color: '#f1416c',
        padding: '14px',
        borderRadius: '20px',
        marginBottom: '1.5rem',
        textAlign: 'center',
        fontSize: '0.85rem'
    },
    form: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem'
    },
    inputGroup: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.8rem'
    },
    label: {
        color: '#00715d',
        fontSize: '0.9rem',
        fontWeight: '800',
        paddingLeft: '4px'
    },
    input: {
        backgroundColor: 'rgba(255, 255, 255, 0.7)',
        border: '1.5px solid rgba(146, 181, 110, 0.3)',
        borderRadius: '20px',
        padding: '1.1rem',
        color: '#00715d',
        fontSize: '1rem',
        outline: 'none',
        transition: 'all 0.3s ease'
    },
    button: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        border: 'none',
        borderRadius: '20px',
        padding: '1.2rem',
        fontSize: '1.1rem',
        fontWeight: '800',
        cursor: 'pointer',
        marginTop: '1.2rem',
        transition: 'all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
        boxShadow: '0 15px 30px rgba(0, 136, 93, 0.3)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        gap: '12px'
    }
};

export default LoginProf;
