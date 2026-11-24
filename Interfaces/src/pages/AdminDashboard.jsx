import React, { useState, useEffect } from 'react';
import { apiCall, BASE_URL } from "../services/api.js";
import { useNavigate } from 'react-router-dom';

const AdminDashboard = () => {
    const [admin, setAdmin] = useState(null);
    const [stats, setStats] = useState({ storage: '0 MB', files: '0', users: '0' });
    const [professors, setProfessors] = useState([]);
    const [loadingProfs, setLoadingProfs] = useState(false);
    const [newProf, setNewProf] = useState({ fullName: '', email: '', password: '' });
    const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
    const [apiResponse, setApiResponse] = useState(null);
    const [loadingAction, setLoadingAction] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'createdAt', direction: 'desc' });
    const [searchQuery, setSearchQuery] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        const fetchAdminData = async () => {
            try {
                const userStr = localStorage.getItem('user');
                if (!userStr) {
                    navigate('/login');
                    return;
                }

                const storedUser = JSON.parse(userStr);
                if (storedUser.role !== 'ADMIN') {
                    localStorage.clear();
                    navigate('/login');
                    return;
                }

                setAdmin(storedUser);
                refreshAll(storedUser.id);
            } catch (error) {
                console.error("Error fetching admin data:", error);
                navigate('/login');
            }
        };
        fetchAdminData();
    }, [navigate]);

    const refreshAll = async (id) => {
        const adminId = id || admin?.id;
        if (!adminId) return;
        refreshStats(adminId);
        fetchProfessors(adminId);
    };

    const refreshStats = async (adminId) => {
        try {
            const storageRes = await apiCall(`/api/admin/dashboard/storage?adminId=${adminId}`);
            const filesRes = await apiCall(`/api/admin/dashboard/files-count?adminId=${adminId}`);
            const profsRes = await apiCall(`/api/admin/professors?adminId=${adminId}`);

            setStats({
                storage: storageRes.success ? (storageRes.data / (1024 * 1024)).toFixed(2) + ' MB' : '0 MB',
                files: filesRes.success ? filesRes.data : '0',
                users: Array.isArray(profsRes) ? profsRes.length : (profsRes.success ? profsRes.data.length : '0')
            });
        } catch (error) {
            console.error("Erreur stats:", error);
        }
    };

    const fetchProfessors = async (adminId) => {
        setLoadingProfs(true);
        try {
            const profsRes = await apiCall(`/api/admin/professors?adminId=${adminId}`);
            const profsBase = Array.isArray(profsRes) ? profsRes : (profsRes.data || []);

            const statsRes = await apiCall(`/api/admin/dashboard/professors-stats?adminId=${adminId}`);
            const statsMap = statsRes.success ? statsRes.data : {};

            const enrichedProfs = profsBase.map(prof => ({
                ...prof,
                courseCount: statsMap[prof.id]?.courses || 0,
                docCount: statsMap[prof.id]?.documents || 0
            }));

            setProfessors(enrichedProfs);
        } catch (error) {
            console.error("Erreur professeurs:", error);
        } finally {
            setLoadingProfs(false);
        }
    };

    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
        setSortConfig({ key, direction });
    };

    const filteredProfessors = professors
        .filter(prof => {
            const query = searchQuery.toLowerCase();
            return (prof.fullName?.toLowerCase().includes(query) || prof.email?.toLowerCase().includes(query));
        })
        .sort((a, b) => {
            let valA = a[sortConfig.key];
            let valB = b[sortConfig.key];
            if (sortConfig.key === 'createdAt') {
                valA = valA ? new Date(valA) : new Date(0);
                valB = valB ? new Date(valB) : new Date(0);
            }
            if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
            if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });

    const handleCreateProf = async (e) => {
        e.preventDefault();
        if (!newProf.fullName || !newProf.email || !newProf.password) {
            showStatus('error', 'Champs requis');
            return;
        }

        try {
            const response = await fetch(`${BASE_URL}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...newProf, role: 'PROFESSOR', parentAdminId: admin.id })
            });

            if (response.ok) {
                showStatus('success', 'Professeur créé !');
                setNewProf({ fullName: '', email: '', password: '' });
                refreshAll();
            } else {
                showStatus('error', 'Échec création');
            }
        } catch (error) {
            showStatus('error', 'Erreur serveur');
        }
    };

    const handleDeleteProf = async (profId) => {
        if (!window.confirm("Supprimer ce professeur ?")) return;
        try {
            const res = await apiCall(`/api/admin/professors/${profId}`, 'DELETE');
            if (res) {
                showStatus('success', 'Supprimé');
                refreshAll();
            }
        } catch (error) {
            showStatus('error', 'Erreur suppression');
        }
    };

    const executeMaintenance = async (endpoint, method = 'POST', logTitle) => {
        setLoadingAction(logTitle);
        setApiResponse(null);
        try {
            const res = await apiCall(`/api/admin/dashboard/maintenance/${endpoint}?adminId=${admin.id}`, method);
            setApiResponse({ title: logTitle, ...res });
            if (res.success) refreshStats(admin.id);
        } catch (error) {
            setApiResponse({ title: logTitle, success: false, message: error.message });
        } finally {
            setLoadingAction(null);
        }
    };

    const showStatus = (type, text) => {
        setStatusMsg({ type, text });
        setTimeout(() => setStatusMsg({ type: '', text: '' }), 4000);
    };

    const handleLogout = () => {
        localStorage.clear();
        navigate('/login');
    };

    const getInitials = (name) => {
        if (!name) return "?";
        const parts = name.trim().split(/\s+/);
        if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
        return name[0].toUpperCase();
    };

    const getAvatarColor = (name) => {
        const colors = ['#00885d', '#599f62', '#92b56e', '#c6ca82', '#f7df9f', '#00715d'];
        let hash = 0;
        const str = name || "User";
        for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
        return colors[Math.abs(hash) % colors.length];
    };

    // Ghost Books animation logic
    const ghostBooks = Array.from({ length: 45 }).map((_, i) => ({
        id: i,
        delay: Math.random() * 20,
        left: 65 + Math.random() * 30,
        size: 15 + Math.random() * 35,
        rotate: Math.random() * 360,
        emoji: ['📚', '📖', '📗', '📘', '📙'][Math.floor(Math.random() * 5)]
    }));

    return (
        <div style={styles.dashboardPage}>
            <style>
                {`
                @keyframes fall {
                    0% { transform: translateY(-100px) rotate(0deg); opacity: 0; }
                    10% { opacity: 0.2; }
                    90% { opacity: 0.2; }
                    100% { transform: translateY(110vh) rotate(360deg); opacity: 0; }
                }
                .maint-btn-container {
                    position: relative;
                    display: inline-block;
                }
                .maint-tooltip {
                    visibility: hidden;
                    width: 220px;
                    background-color: #004d3e;
                    color: #fff;
                    text-align: center;
                    border-radius: 12px;
                    padding: 10px;
                    position: absolute;
                    z-index: 2000; // Passage au premier plan absolu
                    top: 130%; // Un peu plus de gap avec le bouton
                    left: 50%;
                    margin-left: -110px;
                    opacity: 0;
                    transition: opacity 0.2s, transform 0.2s;
                    transform: translateY(-10px);
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                    font-size: 0.75rem;
                    line-height: 1.4;
                    pointer-events: none;
                    font-weight: 500;
                    border: 1px solid rgba(255,255,255,0.1);
                }
                .maint-tooltip::after {
                    content: "";
                    position: absolute;
                    bottom: 100%;
                    left: 50%;
                    margin-left: -5px;
                    border-width: 5px;
                    border-style: solid;
                    border-color: transparent transparent #004d3e transparent;
                }
                .maint-btn-container:hover .maint-tooltip {
                    visibility: visible;
                    opacity: 1;
                    transform: translateY(0);
                }
                `}
            </style>
            
            {/* Ghost Books Background */}
            <div style={styles.ghostContainer}>
                {ghostBooks.map(book => (
                    <span key={book.id} style={{
                        ...styles.ghostBook,
                        left: `${book.left}%`,
                        fontSize: `${book.size}px`,
                        animationDelay: `${book.delay}s`,
                        transform: `rotate(${book.rotate}deg)`
                    }}>
                        {book.emoji}
                    </span>
                ))}
            </div>

            <header style={styles.header}>
                <div style={styles.logo}>AI Assistant <span style={styles.adminBadge}>Admin</span></div>
                <div style={styles.userInfo}>
                    <div style={{textAlign: 'right'}}>
                        <div style={{fontWeight: '800'}}>{admin?.fullName}</div>
                        <div style={{fontSize: '0.7rem', color: '#599f62', fontWeight: '900'}}>SUPERVISEUR</div>
                    </div>
                    <button onClick={handleLogout} style={styles.logoutBtn}>Déconnexion</button>
                </div>
            </header>

            <main style={styles.mainContent}>
                <div style={styles.topRow}>
                    <div style={styles.statsGrid}>
                        <StatCard label="Disque" value={stats.storage} icon="💾" />
                        <StatCard label="Indexé" value={stats.files} icon="🧠" />
                        <StatCard label="Staff" value={stats.users} icon="👨‍🏫" />
                    </div>
                    
                    <section style={styles.maintenanceRow}>
                        <div style={styles.maintenanceHeaderSlim}>
                            <h2 style={styles.sectionTitleSmall}>⚙️ Maintenance</h2>
                            <div style={styles.maintenanceButtonsHorizontal}>
                                <MaintenanceBtn 
                                    label="Audit Intégrité" 
                                    onClick={() => executeMaintenance('validate', 'GET', 'Audit')} 
                                    loading={loadingAction === 'Audit'}
                                    help="Vérifie les liens morts dans la base de données GridFS pour s'assurer que tous les fichiers physiques existent."
                                />
                                <MaintenanceBtn 
                                    label="Nettoyage Orphelins" 
                                    onClick={() => executeMaintenance('clean-orphans', 'POST', 'Ménage')}
                                    loading={loadingAction === 'Ménage'}
                                    help="Supprime définitivement les fichiers sur le disque qui ne sont plus référencés par aucun cours."
                                />
                                <MaintenanceBtn 
                                    label="IA Fix (Vecteurs)" 
                                    onClick={() => executeMaintenance('sync-qdrant', 'POST', 'IA Fix')}
                                    loading={loadingAction === 'IA Fix'}
                                    isSpecial
                                    help="Synchronise l'index Qdrant avec MongoDB pour corriger les erreurs de recherche vectorielle."
                                />
                            </div>
                        </div>
                    </section>
                </div>

                <div style={styles.dashboardGrid}>
                    <section style={styles.profSection}>
                        <div style={styles.sectionHeader}>
                            <h2 style={styles.sectionTitle}>👨‍🏫 Équipe Enseignante</h2>
                            <div style={styles.searchBox}>
                                <input
                                    placeholder="Rechercher..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    style={styles.searchInput}
                                />
                                <span style={styles.countBadge}>{filteredProfessors.length}</span>
                            </div>
                        </div>
                        
                        <div style={styles.tableWrapper}>
                            <table style={styles.table}>
                                <thead>
                                    <tr style={styles.thRow}>
                                        <th style={styles.th} onClick={() => handleSort('fullName')}>Nom Complet</th>
                                        <th style={styles.th}>Contact Email</th>
                                        <th style={styles.thCenter}>Cours</th>
                                        <th style={styles.thCenter}>Docs</th>
                                        <th style={{...styles.th, textAlign: 'right'}}>Gestion</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loadingProfs ? (
                                        <tr><td colSpan="5" style={styles.loadingTd}>Chargement sécurisé...</td></tr>
                                    ) : filteredProfessors.map(prof => (
                                        <tr key={prof.id} style={styles.tr}>
                                            <td style={styles.td}>
                                                <div style={styles.profNameCell}>
                                                    <div style={{
                                                        ...styles.avatarCircle,
                                                        backgroundColor: getAvatarColor(prof.fullName)
                                                    }}>
                                                        {getInitials(prof.fullName)}
                                                    </div>
                                                    <span style={styles.profNameText}>{prof.fullName}</span>
                                                </div>
                                            </td>
                                            <td style={styles.tdEmail}>{prof.email}</td>
                                            <td style={styles.tdCenter}>{prof.courseCount}</td>
                                            <td style={styles.tdCenter}>{prof.docCount}</td>
                                            <td style={{...styles.td, textAlign: 'right'}}>
                                                <button onClick={() => handleDeleteProf(prof.id)} style={styles.deleteBtn}>✖</button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </section>

                    <aside style={styles.sidebar}>
                        <section style={styles.createCard}>
                            <h2 style={styles.sidebarTitle}>➕ Nouveau Professeur</h2>
                            <form onSubmit={handleCreateProf} style={styles.verticalForm}>
                                <div style={styles.fieldGroup}>
                                    <label style={styles.label}>NOM COMPLET</label>
                                    <input
                                        placeholder="Dr. Jean Dupont"
                                        value={newProf.fullName}
                                        onChange={(e) => setNewProf({...newProf, fullName: e.target.value})}
                                        style={styles.inputVertical}
                                    />
                                </div>
                                <div style={styles.fieldGroup}>
                                    <label style={styles.label}>EMAIL PRO</label>
                                    <input
                                        placeholder="nom@ecole.com"
                                        type="email"
                                        value={newProf.email}
                                        onChange={(e) => setNewProf({...newProf, email: e.target.value})}
                                        style={styles.inputVertical}
                                    />
                                </div>
                                <div style={styles.fieldGroup}>
                                    <label style={styles.label}>MOT DE PASSE</label>
                                    <input
                                        placeholder="••••••••"
                                        type="password"
                                        value={newProf.password}
                                        onChange={(e) => setNewProf({...newProf, password: e.target.value})}
                                        style={styles.inputVertical}
                                    />
                                </div>
                                <button type="submit" style={styles.primaryBtnVertical}>Inscrire le Compte</button>
                            </form>
                        </section>

                        {apiResponse && (
                            <section style={styles.consoleCard}>
                                <div style={styles.consoleHeader}>
                                    <span>CONSOLE</span>
                                    <button onClick={() => setApiResponse(null)} style={{background: 'none', border: 'none', color: '#fff', cursor: 'pointer'}}>✖</button>
                                </div>
                                <pre style={styles.pre}>
                                    {JSON.stringify(apiResponse, null, 2)}
                                </pre>
                            </section>
                        )}
                    </aside>
                </div>
            </main>
        </div>
    );
};

const StatCard = ({ label, value, icon }) => (
    <div style={styles.statCard}>
        <div style={styles.statIcon}>{icon}</div>
        <div style={styles.statContent}>
            <div style={styles.statValue}>{value}</div>
            <div style={styles.statLabel}>{label}</div>
        </div>
    </div>
);

const MaintenanceBtn = ({ label, onClick, loading, isSpecial, help }) => (
    <div className="maint-btn-container">
        <button 
            onClick={onClick} 
            disabled={loading}
            style={{
                ...styles.maintBtn, 
                ...(isSpecial ? styles.maintBtnSpecial : {}),
                opacity: loading ? 0.5 : 1
            }}
        >
            {loading ? "..." : label}
        </button>
        <div className="maint-tooltip">{help}</div>
    </div>
);

const styles = {
    dashboardPage: {
        background: 'radial-gradient(circle at 15% 15%, #f7df9f 0%, #92b56e 50%, #00715d 100%)',
        minHeight: '100vh',
        color: '#00715d',
        fontFamily: 'Inter, sans-serif',
        paddingTop: '60px',
        position: 'relative',
        overflowX: 'hidden'
    },
    ghostContainer: {
        position: 'fixed',
        top: 0, right: 0, bottom: 0, left: 0,
        pointerEvents: 'none',
        zIndex: 0,
        overflow: 'hidden'
    },
    ghostBook: {
        position: 'absolute',
        top: '-100px',
        opacity: 0,
        animation: 'fall 25s linear infinite',
        willChange: 'transform, opacity',
        pointerEvents: 'none'
    },
    header: {
        position: 'fixed',
        top: 0, left: 0, right: 0,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.8rem 2.5rem',
        backgroundColor: 'rgba(217, 237, 223, 0.8)',
        backdropFilter: 'blur(15px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.3)',
        zIndex: 1100, // Augmenté pour être au dessus des tooltips si besoin
        boxShadow: '0 10px 30px rgba(0, 71, 93, 0.1)'
    },
    logo: {
        fontSize: '1.4rem',
        fontWeight: '900',
        letterSpacing: '-1px',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem'
    },
    adminBadge: {
        fontSize: '0.6rem',
        backgroundColor: '#00715d',
        color: '#fff',
        padding: '2px 8px',
        borderRadius: '20px',
        fontWeight: '900',
        verticalAlign: 'middle'
    },
    userInfo: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.5rem',
        color: '#00715d'
    },
    logoutBtn: {
        backgroundColor: '#f1416c',
        color: '#ffffff',
        border: 'none',
        padding: '0.5rem 1.2rem',
        borderRadius: '12px',
        cursor: 'pointer',
        fontWeight: 'bold',
        fontSize: '0.85rem'
    },
    mainContent: {
        padding: '12px 2.5rem 2.5rem 2.5rem', // Cap de 12px (3mm) sous le header
        maxWidth: '1400px',
        margin: '0 auto',
        position: 'relative',
        zIndex: 1
    },
    topRow: {
        display: 'flex',
        gap: '1rem',
        marginBottom: '38px', // Aération de 1cm (38px)
        alignItems: 'stretch'
    },
    statsGrid: {
        display: 'flex',
        gap: '1rem',
        flex: 1
    },
    statCard: {
        flex: 1,
        backgroundColor: 'rgba(255, 255, 255, 0.4)',
        backdropFilter: 'blur(10px)',
        padding: '1rem',
        borderRadius: '20px',
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        border: '1px solid rgba(255, 255, 255, 0.3)',
        boxShadow: '0 15px 30px rgba(0, 0, 0, 0.05)'
    },
    statIcon: { fontSize: '1.5rem', opacity: 0.8 },
    statValue: { fontSize: '1.1rem', fontWeight: '900', color: '#00715d' },
    statLabel: { fontSize: '0.65rem', color: '#599f62', fontWeight: '900', textTransform: 'uppercase' },

    maintenanceRow: {
        backgroundColor: 'rgba(255, 255, 255, 0.5)',
        backdropFilter: 'blur(15px)',
        padding: '0.6rem 1.5rem',
        borderRadius: '20px',
        border: '1px solid rgba(255, 255, 255, 0.4)',
        flex: 1.5,
        display: 'flex',
        alignItems: 'center'
    },
    maintenanceHeaderSlim: {
        width: '100%',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
    },
    maintenanceButtonsHorizontal: {
        display: 'flex',
        gap: '0.6rem'
    },
    sectionTitleSmall: {
        color: '#00715d',
        fontSize: '0.9rem',
        fontWeight: '900',
        margin: 0,
        textTransform: 'uppercase'
    },

    dashboardGrid: {
        display: 'grid',
        gridTemplateColumns: '1fr 320px',
        gap: '1rem',
        marginTop: '2cm'
    },
    profSection: {
        backgroundColor: 'rgba(217, 237, 223, 0.6)',
        backdropFilter: 'blur(20px)',
        borderRadius: '30px',
        border: '1px solid rgba(255, 255, 255, 0.4)',
        padding: '1.2rem',
        boxShadow: '0 30px 60px rgba(0, 71, 93, 0.08)'
    },
    sectionHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '0.8rem'
    },
    sectionTitle: { fontSize: '1.2rem', fontWeight: '900', margin: 0 },
    searchBox: { display: 'flex', alignItems: 'center', gap: '0.5rem' },
    searchInput: {
        padding: '0.6rem 1.2rem',
        borderRadius: '12px',
        border: '2px solid rgba(0, 113, 93, 0.2)', // Bordure plus visible
        fontSize: '0.85rem',
        width: '360px', // Longueur doublée
        outline: 'none',
        backgroundColor: '#fff', // Fond blanc pour contraste max
        boxShadow: '0 4px 10px rgba(0,0,0,0.05)',
        color: '#00715d',
        fontWeight: '600'
    },
    countBadge: {
        backgroundColor: '#00715d',
        color: '#fff',
        padding: '3px 8px',
        borderRadius: '10px',
        fontSize: '0.7rem',
        fontWeight: '900'
    },
    tableWrapper: {
        backgroundColor: 'rgba(255, 255, 255, 0.3)',
        borderRadius: '20px',
        overflow: 'hidden'
    },
    table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.95rem' }, // Augmenté
    th: {
        textAlign: 'left',
        padding: '0.8rem 1rem',
        fontSize: '0.8rem', // Augmenté
        textTransform: 'uppercase',
        fontWeight: '900',
        backgroundColor: 'rgba(0, 136, 93, 0.05)',
        cursor: 'pointer'
    },
    thCenter: { textAlign: 'center', padding: '0.8rem', fontSize: '0.8rem', fontWeight: '900', backgroundColor: 'rgba(0, 136, 93, 0.05)' },
    tr: { borderBottom: '1px solid rgba(0, 113, 93, 0.05)', height: '65px' },
    td: { padding: '0.8rem 1rem', verticalAlign: 'middle' },
    profNameCell: { 
        display: 'flex', 
        alignItems: 'center', 
        gap: '1rem' 
    },
    avatarCircle: {
        width: '38px',
        height: '38px',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontWeight: '900',
        fontSize: '0.85rem',
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        border: '1.5px solid rgba(255,255,255,0.3)',
        flexShrink: 0,
        textShadow: '0 1px 2px rgba(0,0,0,0.2)'
    },
    profNameText: { 
        fontWeight: '800',
        color: '#00715d',
        fontSize: '1rem' // Augmenté
    },
    tdEmail: { padding: '0.8rem 1rem', color: '#599f62', fontSize: '0.85rem', verticalAlign: 'middle' }, // Augmenté
    tdCenter: { padding: '0.8rem', textAlign: 'center', fontWeight: '900', color: '#00885d', verticalAlign: 'middle' },
    deleteBtn: {
        background: 'none', border: 'none', color: '#f1416c', fontWeight: '900', cursor: 'pointer', fontSize: '1.1rem'
    },

    sidebar: { display: 'flex', flexDirection: 'column', gap: '1rem' },
    createCard: {
        backgroundColor: 'rgba(255, 255, 255, 0.4)',
        backdropFilter: 'blur(10px)',
        padding: '1.2rem',
        borderRadius: '30px',
        border: '1px solid rgba(255, 255, 255, 0.2)'
    },
    sidebarTitle: { fontSize: '1.05rem', fontWeight: '900', marginBottom: '1rem', color: '#00715d' }, // Augmenté
    verticalForm: { display: 'flex', flexDirection: 'column', gap: '0.8rem' },
    fieldGroup: { display: 'flex', flexDirection: 'column', gap: '0.3rem' },
    label: { fontSize: '0.75rem', fontWeight: '900', color: '#599f62', marginLeft: '0.3rem' }, // Augmenté
    inputVertical: {
        padding: '0.6rem 0.8rem',
        borderRadius: '12px',
        border: '1px solid rgba(0, 113, 93, 0.1)',
        backgroundColor: 'rgba(255, 255, 255, 0.6)',
        fontSize: '0.92rem', // Augmenté
        outline: 'none'
    },
    primaryBtnVertical: {
        backgroundColor: '#00885d',
        color: '#fff',
        border: 'none',
        padding: '0.8rem',
        borderRadius: '12px',
        fontWeight: '900',
        fontSize: '0.92rem', // Ajouté
        cursor: 'pointer',
        marginTop: '0.4rem',
        boxShadow: '0 10px 20px rgba(0, 136, 93, 0.1)'
    },

    maintBtn: {
        padding: '0.8rem 1.6rem', // Beaucoup plus gros
        borderRadius: '15px',
        border: '1px solid rgba(0, 113, 93, 0.1)',
        background: 'rgba(255, 255, 255, 0.7)',
        cursor: 'pointer',
        fontSize: '0.95rem', // Texte plus imposant
        fontWeight: '900',
        color: '#00715d',
        transition: 'all 0.3s ease',
        boxShadow: '0 4px 15px rgba(0,0,0,0.05)'
    },
    maintBtnSpecial: {
        backgroundColor: '#00885d',
        color: '#fff',
        borderColor: '#00885d'
    },
    consoleCard: {
        backgroundColor: '#050508',
        padding: '1rem',
        borderRadius: '20px',
        color: '#00d084',
        fontSize: '0.7rem'
    },
    consoleHeader: { display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontWeight: '900', color: '#599f62' },
    pre: { margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }
};

export default AdminDashboard;