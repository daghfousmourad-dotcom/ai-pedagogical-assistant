// ==============================================================================
// PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
// Système d'Interaction Vocale Intelligent pour l'Éducation
// ------------------------------------------------------------------------------
// Ce fichier est confidentiel et protégé par les lois sur la propriété 
// intellectuelle. Toute diffusion non autorisée est passible de poursuites.
// ==============================================================================
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiCall, BASE_URL } from '../services/api';

const FASTAPI_URL = 'http://localhost:5005'; // URL directe FastAPI pour le polling de progression

const ProfDashboard = () => {
    const [courses, setCourses] = useState([]);
    const [loading, setLoading] = useState(true);
    const [userEmail, setUserEmail] = useState('');
    const [newCourseTitle, setNewCourseTitle] = useState('');
    const [uploadingCourseId, setUploadingCourseId] = useState(null);
    const [uploadStatuses, setUploadStatuses] = useState({}); // { courseId: 'IDLE' | 'UPLOADING' | 'SUCCESS' | 'FAILED' }
    const [indexingProgress, setIndexingProgress] = useState({}); // { courseId: { percent: 0, current: 0, total: 0, state: 'PROGRESS' } }
    const pollingIntervalsRef = useRef({}); // Références aux intervals de polling actifs
    const [selectedCourse, setSelectedCourse] = useState(null);
    const [courseDocs, setCourseDocs] = useState([]);
    const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
    const [profileForm, setProfileForm] = useState({ fullName: '', email: '', password: '' });
    const [editingField, setEditingField] = useState(null); // { docId, field: 'domain' | 'role' }
    const [editValue, setEditValue] = useState('');
    const navigate = useNavigate();

    // The user's JWT ID is encoded in the JWT, which the gateway handles, 
    // but we can parse the JWT locally or send a generic request. 
    // For now, we get the profile from localStorage and assume standard gateway behavior.
    useEffect(() => {
        const token = localStorage.getItem('token');
        const userStr = localStorage.getItem('user');

        if (!token || !userStr) {
            navigate('/login');
            return;
        }

        try {
            const user = JSON.parse(userStr);
            if (user.role !== 'PROFESSOR' && user.role !== 'ADMIN') {
                console.error("Accès refusé : rôle incorrect");
                navigate('/login');
                return;
            }

            setUserEmail(user.email || 'Professeur');

            // Extraction de l'ID pour charger les cours
            if (user.id) {
                fetchCourses(user.id);
                setProfileForm({ fullName: user.fullName || '', email: user.email || '', password: '' });
            } else {
                console.warn("Aucun ID de professeur trouvé");
                setLoading(false);
            }
        } catch (error) {
            console.error("Erreur de session:", error);
            navigate('/login');
        }
    }, [navigate]);

    const fetchCourses = async (profId) => {
        setLoading(true);
        try {
            const res = await apiCall(`/api/courses/${profId}`);
            setCourses(res.data || []);
        } catch (err) {
            console.error("Impossible de charger les cours", err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateCourse = async (e) => {
        e.preventDefault();
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        if (!profId || !newCourseTitle) return;

        try {
            const res = await apiCall(`/api/courses/${profId}/create?title=${encodeURIComponent(newCourseTitle)}`, 'POST');
            if (res.success) {
                setCourses([...courses, res.data]);
                setNewCourseTitle('');
            }
        } catch (err) {
            alert("Erreur lors de la création du cours");
        }
    };

    const handleFileUpload = async (courseId, file, method = 1) => {
        if (!file) return;
        setUploadingCourseId(courseId);
        setUploadStatuses(prev => ({ ...prev, [courseId]: 'UPLOADING' }));
        setIndexingProgress(prev => ({ ...prev, [courseId]: { percent: 0, state: 'UPLOADING' } }));

        const formData = new FormData();
        formData.append('file', file);
        formData.append('method', method);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${BASE_URL}/api/courses/${courseId}/upload`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            if (response.ok) {
                const responseData = await response.json();
                console.log('🔍 [DEBUG] Réponse Java complète:', JSON.stringify(responseData));
                
                // MongoDB peut retourner 'id' ou '_id' selon la sérialisation
                const mongoId = responseData?.data?.id || responseData?.data?._id;
                console.log('🔍 [DEBUG] mongo_id extrait:', mongoId);

                setUploadStatuses(prev => ({ ...prev, [courseId]: 'INDEXING' }));

                if (mongoId) {
                    console.log(`🔄 [DEBUG] Démarrage polling FastAPI pour doc: ${mongoId}`);
                    if (pollingIntervalsRef.current[courseId]) {
                        clearInterval(pollingIntervalsRef.current[courseId]);
                    }

                    pollingIntervalsRef.current[courseId] = setInterval(async () => {
                        try {
                            const pollUrl = `${FASTAPI_URL}/api/ai/doc-progress/${mongoId}`;
                            console.log(`📡 [DEBUG] Poll → ${pollUrl}`);
                            const statusRes = await fetch(pollUrl);
                            const statusData = await statusRes.json();
                            console.log(`📊 [DEBUG] Progression:`, statusData);

                            setIndexingProgress(prev => ({ ...prev, [courseId]: statusData }));

                            if (statusData.state === 'SUCCESS') {
                                clearInterval(pollingIntervalsRef.current[courseId]);
                                delete pollingIntervalsRef.current[courseId];
                                setUploadStatuses(prev => ({ ...prev, [courseId]: 'SUCCESS' }));
                                const storedUser = JSON.parse(localStorage.getItem('user'));
                                if (storedUser?.id) fetchCourses(storedUser.id);
                                setTimeout(() => {
                                    setUploadStatuses(prev => ({ ...prev, [courseId]: 'IDLE' }));
                                    setIndexingProgress(prev => { const n = {...prev}; delete n[courseId]; return n; });
                                }, 3000);
                            } else if (statusData.state === 'FAILURE') {
                                clearInterval(pollingIntervalsRef.current[courseId]);
                                delete pollingIntervalsRef.current[courseId];
                                setUploadStatuses(prev => ({ ...prev, [courseId]: 'FAILED' }));
                            }
                        } catch (e) {
                            console.warn('[Polling] Erreur:', e.message);
                        }
                    }, 1500);
                } else {
                    // Fallback : pas de mongo_id reçu
                    setUploadStatuses(prev => ({ ...prev, [courseId]: 'SUCCESS' }));
                    const storedUser = JSON.parse(localStorage.getItem('user'));
                    if (storedUser?.id) await fetchCourses(storedUser.id);
                    setTimeout(() => setUploadStatuses(prev => ({ ...prev, [courseId]: 'IDLE' })), 3000);
                }
            } else {
                setUploadStatuses(prev => ({ ...prev, [courseId]: 'FAILED' }));
                alert("Échec de l'upload.");
            }
        } catch (err) {
            console.error(err);
            setUploadStatuses(prev => ({ ...prev, [courseId]: 'FAILED' }));
            alert("Erreur d'importation");
        } finally {
            setUploadingCourseId(null);
        }
    };


    const handleDeleteCourse = async (courseId) => {
        if (!window.confirm("Voulez-vous vraiment supprimer ce cours ? L'action est irréversible.")) return;
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        try {
            await apiCall(`/api/courses/${profId}/${courseId}`, 'DELETE');
            setCourses(courses.filter(c => c.id !== courseId));
        } catch (err) {
            alert("Erreur lors de la suppression du cours");
        }
    };

    const openManageDocuments = async (course) => {
        setSelectedCourse(course);
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        try {
            const res = await apiCall(`/api/courses/${profId}/${course.id}/documents`);
            setCourseDocs(res.data || []);
        } catch (err) {
            console.error(err);
            setCourseDocs([]);
        }
    };

    const closeManageDocuments = () => {
        setSelectedCourse(null);
        setCourseDocs([]);
    };

    const handleDeleteDoc = async (docId) => {
        if (!window.confirm("Supprimer ce document ?")) return;
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        try {
            await apiCall(`/api/courses/${profId}/documents/${docId}`, 'DELETE');
            // Optimistic UI update or refresh all
            setCourseDocs(courseDocs.filter(d => d.id !== docId));
            fetchCourses(profId); // Refresh main list to update counts/files
        } catch (err) {
            alert("Erreur lors de la suppression du document");
        }
    };

    const handleRenameDoc = async (docId, currentName) => {
        const newName = window.prompt("Nouveau nom:", currentName);
        if (!newName || newName === currentName) return;
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        try {
            await apiCall(`/api/courses/${profId}/documents/${docId}/rename`, 'PUT', { newName });
            setCourseDocs(courseDocs.map(d => d.id === docId ? { ...d, nom: newName } : d));
        } catch (err) {
            alert("Erreur lors du renommage");
        }
    };

    const handleRenameCourse = async (courseId, currentTitle) => {
        const newTitle = window.prompt("Nouveau titre du cours:", currentTitle);
        if (!newTitle || newTitle === currentTitle) return;

        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;

        try {
            const res = await apiCall(`/api/courses/${profId}/${courseId}`, 'PUT', { title: newTitle });
            if (res.success) {
                setCourses(courses.map(c => c.id === courseId ? { ...c, titre: newTitle } : c));
            }
        } catch (err) {
            alert("Erreur lors du renommage du cours");
        }
    };

    const handleSaveMetadata = async (courseId, docId, field, newValue) => {
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const profId = storedUser.id;
        if (!profId) return;

        const body = field === 'domain'
            ? { courseContext: newValue }
            : { systemRole: newValue };

        try {
            await apiCall(`/api/courses/${courseId}/documents/${docId}/metadata`, 'PATCH', body);
            
            // Mettre à jour l'état local
            setCourses(prevCourses => prevCourses.map(c => {
                if (c.id === courseId) {
                    return {
                        ...c,
                        documents: c.documents.map(d => {
                            if (d.id === docId) {
                                return field === 'domain'
                                    ? { ...d, courseContext: newValue }
                                    : { ...d, systemRole: newValue };
                            }
                            return d;
                        })
                    };
                }
                return c;
            }));
            setEditingField(null);
        } catch (err) {
            console.error("Erreur de sauvegarde métadonnées:", err);
            alert("Erreur lors de la sauvegarde des métadonnées");
        }
    };

    const handleKeyDown = (e, courseId, docId, field) => {
        if (e.key === 'Enter') {
            handleSaveMetadata(courseId, docId, field, editValue);
        } else if (e.key === 'Escape') {
            setEditingField(null);
        }
    };

    const handleUpdateProfile = async (e) => {
        e.preventDefault();
        const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
        const userId = storedUser.id;

        try {
            const res = await apiCall(`/auth/users/${userId}`, 'PUT', profileForm);
            if (res) {
                alert("Profil mis à jour avec succès !");
                // Update local storage and state
                const newUser = { ...storedUser, fullName: res.fullName, email: res.email };
                localStorage.setItem('user', JSON.stringify(newUser));
                setUserEmail(res.email);
                setIsProfileModalOpen(false);
            }
        } catch (err) {
            alert("Erreur lors de la mise à jour du profil");
        }
    };

    const logout = () => {
        localStorage.clear();
        navigate('/login');
    };

    const filteredCourses = courses.filter(c => 
        c.titre.toLowerCase().includes(newCourseTitle.toLowerCase())
    );

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
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                @keyframes fall {
                    0% { transform: translateY(-100px) rotate(0deg); opacity: 0; }
                    10% { opacity: 0.2; }
                    90% { opacity: 0.2; }
                    100% { transform: translateY(110vh) rotate(360deg); opacity: 0; }
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
                <div style={styles.logo}>AI Assistant</div>
                <div style={styles.userInfo}>
                    <button onClick={() => setIsProfileModalOpen(true)} style={styles.profileBtn}>Mon Profil</button>
                    <span>{userEmail}</span>
                    <button onClick={logout} style={styles.logoutBtn}>Déconnexion</button>
                </div>
            </header>

            <main style={styles.mainContent}>
                <section style={styles.createSection}>
                    <h2 style={{color: '#00715d', fontSize: '1.2rem', fontWeight: '800', marginBottom: '0.4rem'}}>➕ Nouveau Cours</h2>
                    <form onSubmit={handleCreateCourse} style={styles.inlineForm}>
                        <input
                            type="text"
                            placeholder="Rechercher ou créer un cours..."
                            value={newCourseTitle}
                            onChange={(e) => setNewCourseTitle(e.target.value)}
                            style={styles.input}
                        />
                        <button type="submit" style={styles.primaryBtn} disabled={!newCourseTitle || filteredCourses.some(c => c.titre.toLowerCase() === newCourseTitle.toLowerCase())}>
                            Créer
                        </button>
                    </form>
                </section>

                <section style={styles.listSection}>
                    <h2 style={{color: '#00715d', fontSize: '1.4rem', fontWeight: '800', marginBottom: '1.2rem'}}>📚 Mes Cours Actifs</h2>
                    {loading ? (
                        <p>Chargement des cours...</p>
                    ) : filteredCourses.length === 0 ? (
                        <div style={styles.emptyState}>
                            {newCourseTitle ? "Aucun cours ne correspond à votre recherche. Cliquez sur 'Créer' pour en ajouter un." : "Aucun cours disponible. Créez-en un pour commencer."}
                        </div>
                    ) : (
                        <div style={styles.gridContainer}>
                            {filteredCourses.map(course => (
                                <div key={course.id} style={styles.courseCard}>
                                    <div style={styles.cardHeader}>
                                        <div style={styles.headerLeft}>
                                            <span style={{fontSize: '1.2rem'}}>📂</span>
                                            <h3 style={styles.courseTitle}>{course.titre}</h3>
                                            <div style={styles.titleActions}>
                                                <button
                                                    onClick={() => handleRenameCourse(course.id, course.titre)}
                                                    style={styles.miniActionBtn}
                                                    title="Renommer"
                                                >
                                                    ✏️
                                                </button>
                                                <button
                                                    onClick={() => openManageDocuments(course)}
                                                    style={styles.miniActionBtn}
                                                    title="Gérer"
                                                >
                                                    ⚙️
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteCourse(course.id)}
                                                    style={{...styles.miniActionBtn, color: '#f1416c'}}
                                                    title="Supprimer"
                                                >
                                                    🗑️
                                                </button>
                                            </div>
                                        </div>
                                        <div style={styles.headerRight}>
                                            <div style={styles.uploadActions}>
                                                <label style={{ ...styles.miniUploadBtn, opacity: uploadingCourseId ? 0.5 : 1 }}>
                                                    + PDF M1
                                                    <input
                                                        type="file"
                                                        accept=".pdf"
                                                        style={{ display: 'none' }}
                                                        onChange={(e) => handleFileUpload(course.id, e.target.files[0], 1)}
                                                        disabled={!!uploadingCourseId}
                                                    />
                                                </label>
                                                <label style={{ ...styles.miniUploadBtnAdvanced, opacity: uploadingCourseId ? 0.5 : 1 }}>
                                                    + PDF M2
                                                    <input
                                                        type="file"
                                                        accept=".pdf"
                                                        style={{ display: 'none' }}
                                                        onChange={(e) => handleFileUpload(course.id, e.target.files[0], 2)}
                                                        disabled={!!uploadingCourseId}
                                                    />
                                                </label>
                                            </div>
                                            <span style={styles.date}>{new Date(course.createdAt).toLocaleDateString()}</span>
                                        </div>
                                    </div>
                                    <div style={styles.cardBody}>
                                        <p style={{ fontWeight: '800', marginBottom: '1rem', fontSize: '0.9rem', color: '#599f62' }}>
                                            📑 Fichiers attachés ({course.docCount || 0}) :
                                        </p>
                                        <div style={styles.tableWrapper}>
                                            {course.documents && course.documents.length > 0 ? (
                                                <table style={styles.filesTable}>
                                                    <thead>
                                                        <tr>
                                                            <th style={styles.th}>Fichier</th>
                                                            <th style={styles.th}>Domaine</th>
                                                            <th style={styles.th}>Rôle Système</th>
                                                            <th style={{...styles.th, textAlign: 'right'}}>Actions</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {course.documents.map(doc => (
                                                            <tr key={doc.id} style={styles.tr}>
                                                                <td style={styles.td}>
                                                                    <span style={styles.fileNameLink}>📄 {doc.nom}</span>
                                                                </td>
                                                                <td style={styles.td}>
                                                                    {editingField && editingField.docId === doc.id && editingField.field === 'domain' ? (
                                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                                                            <input
                                                                                type="text"
                                                                                className="inline-input"
                                                                                value={editValue}
                                                                                onChange={(e) => setEditValue(e.target.value)}
                                                                                onKeyDown={(e) => handleKeyDown(e, course.id, doc.id, 'domain')}
                                                                                autoFocus
                                                                            />
                                                                            <button 
                                                                                onClick={() => handleSaveMetadata(course.id, doc.id, 'domain', editValue)} 
                                                                                className="save-btn-mini"
                                                                                title="Enregistrer"
                                                                            >
                                                                                ✓
                                                                            </button>
                                                                            <button 
                                                                                onClick={() => setEditingField(null)} 
                                                                                className="cancel-btn-mini"
                                                                                title="Annuler"
                                                                            >
                                                                                ✗
                                                                            </button>
                                                                        </div>
                                                                    ) : (
                                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                                                                            <span style={styles.domainBadge}>
                                                                                {doc.courseContext || "Analyse..."}
                                                                            </span>
                                                                            <button
                                                                                onClick={() => {
                                                                                    setEditingField({ docId: doc.id, field: 'domain' });
                                                                                    setEditValue(doc.courseContext || "");
                                                                                }}
                                                                                className="edit-btn-mini"
                                                                                title="Modifier le domaine"
                                                                            >
                                                                                ✏️
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                </td>
                                                                <td style={styles.td}>
                                                                    {editingField && editingField.docId === doc.id && editingField.field === 'role' ? (
                                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', width: '100%' }}>
                                                                            <input
                                                                                type="text"
                                                                                className="inline-input"
                                                                                style={{ width: '100%', maxWidth: '300px' }}
                                                                                value={editValue}
                                                                                onChange={(e) => setEditValue(e.target.value)}
                                                                                onKeyDown={(e) => handleKeyDown(e, course.id, doc.id, 'role')}
                                                                                autoFocus
                                                                            />
                                                                            <button 
                                                                                onClick={() => handleSaveMetadata(course.id, doc.id, 'role', editValue)} 
                                                                                className="save-btn-mini"
                                                                                title="Enregistrer"
                                                                            >
                                                                                ✓
                                                                            </button>
                                                                            <button 
                                                                                onClick={() => setEditingField(null)} 
                                                                                className="cancel-btn-mini"
                                                                                title="Annuler"
                                                                            >
                                                                                ✗
                                                                            </button>
                                                                        </div>
                                                                    ) : (
                                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', width: '100%' }}>
                                                                            <div style={styles.rolePreview} title={doc.systemRole}>
                                                                                {doc.systemRole || "Analyse..."}
                                                                            </div>
                                                                            <button
                                                                                onClick={() => {
                                                                                    setEditingField({ docId: doc.id, field: 'role' });
                                                                                    setEditValue(doc.systemRole || "");
                                                                                }}
                                                                                className="edit-btn-mini"
                                                                                title="Modifier le rôle système"
                                                                            >
                                                                                ✏️
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                </td>
                                                                <td style={{...styles.td, textAlign: 'right'}}>
                                                                    <div style={styles.docActionsTable}>
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); window.open(`${window.location.origin}/session/${course.id}/${doc.id}`, '_blank'); }}
                                                                            style={styles.launchBtn}
                                                                        >
                                                                            Lancer
                                                                        </button>
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); window.open(`${window.location.origin}/super-session/${course.id}/${doc.id}`, '_blank'); }}
                                                                            style={styles.superBtn}
                                                                        >
                                                                            Super_IA
                                                                        </button>
                                                                        <button
                                                                            onClick={(e) => { e.stopPropagation(); handleDeleteDoc(doc.id); }}
                                                                            style={styles.miniDeleteBtn}
                                                                            title="Supprimer le document"
                                                                        >
                                                                            ✖
                                                                        </button>
                                                                    </div>
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            ) : (
                                                <p style={styles.noFiles}>Aucun PDF attaché.</p>
                                            )}
                                        </div>
                                        
                                        {/* Barre de progression d'indexation */}
                                        {(uploadStatuses[course.id] === 'INDEXING' || uploadStatuses[course.id] === 'UPLOADING') && (
                                            <div style={{marginTop: '1.5rem'}}>
                                                {uploadStatuses[course.id] === 'INDEXING' && (
                                                    <div style={styles.progressContainer}>
                                                        <div style={styles.progressHeader}>
                                                            <span style={styles.progressLabel}>⚙️ Vectorisation IA...</span>
                                                            <span style={styles.progressPercent}>{indexingProgress[course.id]?.percent ?? 0}%</span>
                                                        </div>
                                                        <div style={styles.progressBarContainer}>
                                                            <div style={{...styles.progressBarFill, width: `${indexingProgress[course.id]?.percent ?? 0}%`}} />
                                                        </div>
                                                    </div>
                                                )}
                                                {uploadStatuses[course.id] === 'UPLOADING' && (
                                                    <div style={styles.uploadProgress}>Envoi du fichier...</div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}

                        </div>
                    )}
                </section>
            </main>

            {/* Document Management Modal */}
            {selectedCourse && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modalContent}>
                        <div style={styles.modalHeader}>
                            <h3>Documents: {selectedCourse.titre}</h3>
                            <button onClick={closeManageDocuments} style={styles.closeModalBtn}>✖</button>
                        </div>
                        <div style={styles.modalBody}>
                            {courseDocs.length === 0 ? (
                                <p style={styles.emptyText}>Aucun document pour ce cours.</p>
                            ) : (
                                <table style={styles.filesTable}>
                                    <thead>
                                        <tr>
                                            <th style={styles.th}>Fichier</th>
                                            <th style={styles.th}>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {courseDocs.map(doc => (
                                            <tr key={doc.id} style={styles.tr}>
                                                <td style={styles.td}>
                                                    <span style={styles.fileNameLink}>{doc.nom}</span>
                                                </td>
                                                <td style={styles.td}>
                                                    <div style={styles.docActions}>
                                                        <button
                                                            onClick={() => handleRenameDoc(doc.id, doc.nom)}
                                                            style={styles.actionIconBtn}
                                                            title="Renommer"
                                                        >
                                                            ✏️
                                                        </button>
                                                        <button
                                                            onClick={() => handleDeleteDoc(doc.id)}
                                                            style={styles.actionIconBtn}
                                                            title="Supprimer"
                                                        >
                                                            🗑️
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Profile Management Modal */}
            {isProfileModalOpen && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modalContent}>
                        <div style={styles.modalHeader}>
                            <h3>Modifier mon Profil</h3>
                            <button onClick={() => setIsProfileModalOpen(false)} style={styles.closeModalBtn}>✖</button>
                        </div>
                        <form onSubmit={handleUpdateProfile} style={styles.modalBody}>
                            <div style={styles.formGroup}>
                                <label style={styles.label}>Nom Complet</label>
                                <input
                                    type="text"
                                    value={profileForm.fullName}
                                    onChange={(e) => setProfileForm({ ...profileForm, fullName: e.target.value })}
                                    style={styles.input}
                                />
                            </div>
                            <div style={styles.formGroup}>
                                <label style={styles.label}>Email</label>
                                <input
                                    type="email"
                                    value={profileForm.email}
                                    onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                                    style={styles.input}
                                />
                            </div>
                            <div style={styles.formGroup}>
                                <label style={styles.label}>Nouveau Mot de Passe (laisser vide pour ne pas changer)</label>
                                <input
                                    type="password"
                                    value={profileForm.password}
                                    onChange={(e) => setProfileForm({ ...profileForm, password: e.target.value })}
                                    style={styles.input}
                                />
                            </div>
                            <button type="submit" style={styles.saveBtn}>Enregistrer les modifications</button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

const styles = {
    dashboardPage: {
        background: 'radial-gradient(circle at 15% 15%, #f7df9f 0%, #92b56e 50%, #00715d 100%)',
        minHeight: '100vh',
        color: '#00715d',
        fontFamily: 'Inter, sans-serif',
        paddingTop: '60px', // Rapproché du header fixe
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
        top: 0,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.8rem 2.5rem', // Plus slim
        backgroundColor: 'rgba(217, 237, 223, 0.8)',
        backdropFilter: 'blur(15px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.3)',
        zIndex: 100,
        boxShadow: '0 10px 30px rgba(0, 71, 93, 0.1)'
    },
    logo: {
        fontSize: '1.4rem', // Plus petit
        fontWeight: '900',
        color: '#00715d',
        letterSpacing: '-1px'
    },
    userInfo: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.2rem',
        color: '#00715d',
        fontWeight: '600',
        fontSize: '0.9rem'
    },
    logoutBtn: {
        backgroundColor: '#f1416c',
        color: '#ffffff',
        border: 'none',
        padding: '0.4rem 1rem', // Plus slim
        borderRadius: '10px',
        cursor: 'pointer',
        fontWeight: 'bold',
        transition: 'all 0.3s ease'
    },
    profileBtn: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        border: 'none',
        padding: '0.4rem 1rem', // Plus slim
        borderRadius: '10px',
        cursor: 'pointer',
        fontWeight: 'bold',
        transition: 'all 0.3s ease'
    },
    mainContent: {
        padding: '8px 2rem 2rem 2rem', // Écart exact de ~2mm avec le header
        maxWidth: '1400px',
        margin: '0 auto'
    },
    createSection: {
        backgroundColor: 'rgba(255, 255, 255, 0.4)',
        backdropFilter: 'blur(10px)',
        padding: '0.8rem 1.5rem', // Hauteur réduite de 50%+
        borderRadius: '20px',
        marginBottom: '1.5rem',
        border: '1px solid rgba(255, 255, 255, 0.3)',
        boxShadow: '0 15px 30px rgba(0, 71, 93, 0.05)'
    },
    inlineForm: {
        display: 'flex',
        gap: '1rem',
        marginTop: '0.5rem'
    },
    input: {
        flex: 1,
        backgroundColor: 'rgba(255, 255, 255, 0.8)',
        border: '1.5px solid rgba(146, 181, 110, 0.3)',
        borderRadius: '12px',
        padding: '0.6rem 1rem', // Plus slim
        color: '#00715d',
        fontSize: '0.95rem',
        outline: 'none'
    },
    primaryBtn: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        border: 'none',
        borderRadius: '12px',
        padding: '0 1.5rem',
        fontWeight: 'bold',
        cursor: 'pointer',
        fontSize: '0.9rem'
    },
    listSection: {
        marginTop: '1rem'
    },
    gridContainer: {
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem',
        marginTop: '1.5rem'
    },
    courseCard: {
        backgroundColor: 'rgba(217, 237, 223, 0.6)',
        backdropFilter: 'blur(20px)',
        borderRadius: '35px',
        border: '1px solid rgba(255, 255, 255, 0.4)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 30px 60px rgba(0, 71, 93, 0.08)'
    },
    cardHeader: {
        padding: '1.5rem 2rem',
        borderBottom: '1px solid rgba(0, 113, 93, 0.1)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'rgba(255, 255, 255, 0.2)'
    },
    headerLeft: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        flex: 1
    },
    headerRight: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.5rem',
        justifyContent: 'flex-end',
        flex: 1
    },
    courseTitle: {
        color: '#00715d',
        margin: 0,
        fontSize: '1.3rem',
        fontWeight: '800'
    },
    titleActions: {
        display: 'flex',
        gap: '0.4rem',
        alignItems: 'center'
    },
    uploadActions: {
        display: 'flex',
        gap: '0.6rem',
        alignItems: 'center'
    },
    miniActionBtn: {
        background: 'rgba(255, 255, 255, 0.5)',
        border: '1px solid rgba(0, 113, 93, 0.1)',
        borderRadius: '8px',
        padding: '0.3rem 0.5rem',
        cursor: 'pointer',
        fontSize: '0.8rem',
        transition: 'all 0.2s'
    },
    miniUploadBtn: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        padding: '0.5rem 1rem',
        borderRadius: '12px',
        cursor: 'pointer',
        fontWeight: '800',
        fontSize: '0.75rem',
        boxShadow: '0 4px 10px rgba(0, 136, 93, 0.2)'
    },
    miniUploadBtnAdvanced: {
        backgroundColor: 'rgba(139, 92, 246, 0.1)',
        color: '#8b5cf6',
        padding: '0.5rem 1rem',
        borderRadius: '12px',
        cursor: 'pointer',
        fontWeight: '800',
        fontSize: '0.75rem',
        border: '1.5px dashed rgba(139, 92, 246, 0.3)'
    },
    date: {
        fontSize: '0.85rem',
        color: '#599f62',
        fontWeight: '600',
        whiteSpace: 'nowrap'
    },
    cardBody: {
        padding: '2rem',
        color: '#00715d'
    },
    tableWrapper: {
        backgroundColor: 'rgba(255, 255, 255, 0.4)',
        borderRadius: '20px',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        overflow: 'hidden'
    },
    filesTable: {
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '0.9rem'
    },
    th: {
        textAlign: 'left',
        padding: '1rem',
        backgroundColor: 'rgba(0, 136, 93, 0.05)',
        color: '#00715d',
        fontWeight: '800',
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        borderBottom: '1px solid rgba(0, 113, 93, 0.1)'
    },
    tr: {
        borderBottom: '1px solid rgba(0, 113, 93, 0.05)'
    },
    td: {
        padding: '1rem',
        verticalAlign: 'middle'
    },
    fileNameLink: {
        fontWeight: '700',
        color: '#00885d'
    },
    domainBadge: {
        display: 'inline-block',
        padding: '4px 12px',
        borderRadius: '20px',
        backgroundColor: 'rgba(0, 136, 93, 0.1)',
        color: '#00885d',
        fontSize: '0.75rem',
        fontWeight: '800'
    },
    docActionsTable: {
        display: 'flex',
        gap: '0.6rem',
        alignItems: 'center',
        justifyContent: 'flex-end'
    },
    launchBtn: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        border: 'none',
        borderRadius: '8px',
        padding: '0.4rem 0.9rem',
        cursor: 'pointer',
        fontWeight: '800',
        fontSize: '0.8rem',
        boxShadow: '0 4px 10px rgba(0, 136, 93, 0.15)',
        transition: 'all 0.2s'
    },
    superBtn: {
        backgroundColor: '#00a876',
        color: '#ffffff',
        border: 'none',
        borderRadius: '8px',
        padding: '0.4rem 0.9rem',
        cursor: 'pointer',
        fontWeight: '800',
        fontSize: '0.8rem',
        boxShadow: '0 4px 10px rgba(0, 168, 118, 0.15)',
        transition: 'all 0.2s'
    },
    miniDeleteBtn: {
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: '1.2rem',
        padding: '0 0.5rem',
        color: '#f1416c',
        fontWeight: '900',
        display: 'flex',
        alignItems: 'center'
    },
    rolePreview: {
        fontSize: '0.8rem',
        color: '#599f62',
        fontStyle: 'italic',
        maxWidth: '350px',
        whiteSpace: 'normal',
        wordBreak: 'break-word'
    },
    modalOverlay: {
        position: 'fixed',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0, 71, 93, 0.4)',
        backdropFilter: 'blur(15px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000
    },
    modalContent: {
        backgroundColor: 'rgba(217, 237, 223, 0.98)',
        width: '90%',
        maxWidth: '550px',
        borderRadius: '40px',
        border: '1px solid rgba(255, 255, 255, 0.5)',
        boxShadow: '0 50px 100px rgba(0, 71, 93, 0.2)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
    },
    modalHeader: {
        padding: '2rem 2.5rem',
        borderBottom: '1px solid rgba(0, 113, 93, 0.1)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
    },
    modalBody: {
        padding: '2.5rem',
        maxHeight: '70vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem'
    },
    closeModalBtn: {
        background: 'none',
        border: 'none',
        color: '#00715d',
        cursor: 'pointer',
        fontSize: '2.2rem',
        lineHeight: 1,
        transition: 'transform 0.2s',
        padding: 0
    },
    formGroup: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem'
    },
    label: {
        fontSize: '0.9rem',
        color: '#00715d',
        fontWeight: '800'
    },
    saveBtn: {
        backgroundColor: '#00885d',
        color: '#ffffff',
        border: 'none',
        borderRadius: '18px',
        padding: '1.2rem',
        fontWeight: '900',
        cursor: 'pointer',
        fontSize: '1.1rem',
        marginTop: '1rem',
        boxShadow: '0 10px 25px rgba(0, 136, 93, 0.2)'
    },
    progressContainer: {
        padding: '1.5rem',
        backgroundColor: 'rgba(255, 255, 255, 0.3)',
        borderRadius: '20px',
        border: '1px solid rgba(0, 208, 132, 0.2)'
    },
    progressBarContainer: {
        width: '100%',
        height: '14px',
        backgroundColor: 'rgba(255, 255, 255, 0.5)',
        borderRadius: '10px',
        overflow: 'hidden'
    },
    progressBarFill: {
        height: '100%',
        backgroundColor: '#00d084',
        borderRadius: '10px',
        transition: 'width 0.5s ease'
    },
    uploadProgress: {
        color: '#00885d',
        fontWeight: '800',
        textAlign: 'center',
        padding: '1rem'
    },
    emptyState: {
        backgroundColor: 'rgba(255, 255, 255, 0.3)',
        padding: '4rem',
        borderRadius: '30px',
        textAlign: 'center',
        color: '#599f62',
        fontSize: '1.1rem',
        border: '2px dashed rgba(255, 255, 255, 0.5)'
    }
};

export default ProfDashboard;
