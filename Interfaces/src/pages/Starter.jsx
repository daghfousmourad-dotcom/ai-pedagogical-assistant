import React, { useState } from 'react';
import { apiCall } from '../services/api';

const FASTAPI_URL = import.meta.env.VITE_FASTAPI_URL || 'http://localhost:5005';

const Starter = () => {
    // --- User Management State ---
    const [fullName, setFullName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [role, setRole] = useState('PROF');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState('');
    const [admins, setAdmins] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [editingAdmin, setEditingAdmin] = useState(null);
    const [isTableLoading, setIsTableLoading] = useState(false);
    const [globalStats, setGlobalStats] = useState({});

    // --- MongoDB Viewer State ---
    const [collections, setCollections] = useState([]);
    const [activeCollection, setActiveCollection] = useState(null);
    const [collectionData, setCollectionData] = useState([]);
    const [isMongoLoading, setIsMongoLoading] = useState(false);
    const [mongoSearchTerm, setMongoSearchTerm] = useState('');

    const fetchAdmins = async () => {
        setIsTableLoading(true);
        try {
            const data = await apiCall('/auth/admins', 'GET');
            const adminsList = Array.isArray(data) ? data : [];
            setAdmins(adminsList);

            // Fetch global stats via Gateway/apiCall
            const statsRes = await apiCall('/api/admin/dashboard/global-stats');
            if (statsRes.success) {
                setGlobalStats(statsRes.data);
            }
        } catch (err) {
            console.error("Failed to fetch admins or stats", err);
        } finally {
            setIsTableLoading(false);
        }
    };

    const fetchCollections = async () => {
        try {
            const res = await fetch(`${FASTAPI_URL}/api/admin/mlops/mongo/collections`);
            const data = await res.json();
            if (data.status === 'success') setCollections(data.collections);
        } catch (e) {
            console.error("Collections error", e);
        }
    };

    const loadCollectionData = async (name) => {
        if (activeCollection === name) {
            setActiveCollection(null);
            setCollectionData([]);
            return;
        }
        setIsMongoLoading(true);
        setActiveCollection(name);
        try {
            const res = await fetch(`${FASTAPI_URL}/api/admin/mlops/mongo/collections/${name}`);
            const data = await res.json();
            if (data.status === 'success') setCollectionData(data.data);
        } catch (e) {
            console.error("Data error", e);
        } finally {
            setIsMongoLoading(false);
        }
    };

    React.useEffect(() => {
        fetchAdmins();
        fetchCollections();
    }, []);

    const handleDelete = async (id) => {
        if (!window.confirm("Êtes-vous sûr de vouloir supprimer cet administrateur ?")) return;
        try {
            await apiCall(`/auth/professors/${id}`, 'DELETE');
            setAdmins(admins.filter(a => a.id !== id));
        } catch (err) {
            alert("Erreur lors de la suppression");
        }
    };

    const handleEdit = (admin) => {
        setEditingAdmin(admin);
        setFullName(admin.fullName);
        setEmail(admin.email);
        setRole(admin.role);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setSuccess(false);
        setError('');

        try {
            let result;
            if (editingAdmin) {
                result = await apiCall(`/auth/users/${editingAdmin.id}`, 'PUT', {
                    fullName,
                    email,
                    password: password || undefined,
                    role
                });
            } else {
                result = await apiCall('/auth/register', 'POST', {
                    fullName,
                    email,
                    password,
                    role
                });
            }

            if (result.success || (result && !result.error && !result.message)) {
                setSuccess(true);
                setFullName('');
                setEmail('');
                setPassword('');
                setRole('PROF');
                setEditingAdmin(null);
                fetchAdmins();
            } else {
                setError(result.message || 'Une erreur est survenue.');
            }
        } catch (err) {
            setError('Impossible de contacter le serveur.');
        } finally {
            setLoading(false);
        }
    };

    const handleLogout = () => {
        localStorage.clear();
        window.location.href = '/admin-login';
    };

    const filteredAdmins = (admins || []).filter(admin =>
        (admin.fullName || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (admin.email || "").toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="min-h-screen bg-gradient-to-br from-[#f0fbff] via-[#bae6fd] to-[#7dd3fc] text-[#004d3e] p-6 font-sans">
            <header className="mb-8 flex justify-between items-center bg-white/40 backdrop-blur-md p-6 rounded-[2.5rem] border border-white/50 shadow-sm">
                <div>
                    <h1 className="text-3xl font-black bg-gradient-to-r from-[#00a3eb] to-[#00715d] bg-clip-text text-transparent">AI Assistant</h1>
                    <p className="text-[#5b8a9f] text-sm font-bold uppercase tracking-wider">Supervision & Administration Centrale</p>
                </div>
                <div className="flex gap-4 items-center">
                    <button 
                        onClick={handleLogout}
                        className="px-6 py-2 bg-white/60 hover:bg-white text-[#f1416c] border border-white rounded-2xl transition-all text-sm font-black flex items-center gap-2 shadow-sm"
                    >
                        <span>🚪</span> Déconnexion
                    </button>
                    <button 
                        onClick={async () => {
                            if (!window.confirm("⚠️ ATTENTION : Cela va nettoyer tous les orphelins GridFS, MongoDB et Qdrant pour TOUS les utilisateurs. Confirmer ?")) return;
                            setLoading(true);
                            try {
                                const res = await apiCall('/api/admin/dashboard/maintenance/total-system-cleanup', 'POST');
                                alert(`Nettoyage réussi !\n` +
                                      `- GridFS (Orphelins) : ${res.data.gridfs_cleaned}\n` +
                                      `- Refs MongoDB (Mortes) : ${res.data.mongo_refs_cleaned}\n` +
                                      `- Qdrant (Fantômes) : ${res.data.qdrant_cleaned}\n` +
                                      `- Docs Mongo (Sans vecteurs) : ${res.data.mongo_hollow_docs_cleaned}`);
                                fetchAdmins();
                            } catch (e) {
                                alert("Échec du nettoyage global");
                            } finally {
                                setLoading(false);
                            }
                        }}
                        disabled={loading}
                        className="px-6 py-2 bg-[#f1416c] hover:bg-[#d9214e] text-white rounded-2xl transition-all text-sm font-black flex items-center gap-2 shadow-lg shadow-rose-200"
                    >
                        {loading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div> : '🧹'} Nettoyage Global
                    </button>
                    <button 
                        onClick={async () => {
                            if (!window.confirm("🔴 DANGER : Cette opération va PURGER (supprimer) TOUTES les données vectorielles de Qdrant. Vous devrez ré-indexer TOUS les documents de TOUS les cours ensuite. Continuer ?")) return;
                            
                            const password = window.prompt("👮 Sécurité de Haute Priorité\nVeuillez saisir votre mot de passe Super Admin pour autoriser la purge de Qdrant :");
                            if (password === null || password.trim() === "") return;
                            
                            setLoading(true);
                            try {
                                const res = await apiCall('/api/admin/dashboard/maintenance/repair-qdrant', 'POST');
                                if (res.success) {
                                    alert("✅ Purge terminée avec succès ! La base vectorielle est réinitialisée.");
                                } else {
                                    alert("❌ Échec de la purge : " + (res.error || "Erreur inconnue"));
                                }
                            } catch (e) {
                                alert("❌ Erreur de communication lors de la purge matérielle");
                            } finally {
                                setLoading(false);
                            }
                        }}
                        disabled={loading}
                        className="px-6 py-2 bg-white/60 hover:bg-white text-[#00a3eb] border border-white rounded-2xl transition-all text-sm font-black flex items-center gap-2 shadow-sm"
                    >
                        {loading ? <div className="w-4 h-4 border-2 border-[#00a3eb]/30 border-t-[#00a3eb] rounded-full animate-spin"></div> : '🔨'} Purger Qdrant
                    </button>
                    <button onClick={() => window.open('/mlops-admin', '_blank')} className="px-6 py-2 bg-white border border-[#9fdaf7] text-[#00a3eb] hover:bg-[#f0fbff] rounded-2xl transition-all text-sm font-black shadow-sm">🔧 MLOps</button>
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Form Section */}
                <div className="lg:col-span-4">
                    <div className="bg-white/60 backdrop-blur-xl border border-white p-8 rounded-[3rem] shadow-xl shadow-blue-100/50">
                        <h2 className="text-xl font-black mb-6 flex items-center gap-3 text-[#00a3eb]">
                             <span className="p-2 bg-blue-100 rounded-2xl">👤</span> {editingAdmin ? 'Modifier' : 'Nouveau'} Compte
                        </h2>
                        <form onSubmit={handleSubmit} className="space-y-4">
                            {success && (
                                <div className="bg-emerald-50 border border-emerald-200 text-emerald-600 p-4 rounded-2xl text-center text-sm font-bold animate-bounce">
                                    ✓ Opération réussie
                                </div>
                            )}
                            {error && (
                                <div className="bg-rose-50 border border-rose-200 text-rose-500 p-4 rounded-2xl text-center text-sm font-bold">
                                    ⚠ {error}
                                </div>
                            )}
                            
                            <div>
                                <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block tracking-widest">Nom Complet</label>
                                <input 
                                    type="text" 
                                    className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-4 outline-none focus:border-[#00a3eb] transition-all text-sm font-bold text-[#004d3e]" 
                                    value={fullName} 
                                    onChange={e => setFullName(e.target.value)} 
                                    required 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block tracking-widest">Adresse Email</label>
                                <input 
                                    type="email" 
                                    className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-4 outline-none focus:border-[#00a3eb] transition-all text-sm font-bold text-[#004d3e]" 
                                    value={email} 
                                    onChange={e => setEmail(e.target.value)} 
                                    required 
                                />
                            </div>
                            <div>
                                <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block tracking-widest">
                                    {editingAdmin ? "Nouveau MDP (Optionnel)" : "Mot de passe"}
                                </label>
                                <input 
                                    type="password" 
                                    className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-4 outline-none focus:border-[#00a3eb] transition-all text-sm font-bold text-[#004d3e]" 
                                    value={password} 
                                    onChange={e => setPassword(e.target.value)} 
                                    required={!editingAdmin} 
                                />
                            </div>
                            
                            {!editingAdmin && (
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block tracking-widest">Rôle Utilisateur</label>
                                    <select 
                                        className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-4 outline-none focus:border-[#00a3eb] transition-all text-sm font-black text-[#004d3e] appearance-none" 
                                        value={role} 
                                        onChange={e => setRole(e.target.value)}
                                    >
                                        <option value="PROF">🎓 Professeur</option>
                                        <option value="ADMIN">🏢 Administrateur (Institution)</option>
                                    </select>
                                </div>
                            )}

                            <div className="flex gap-3 pt-4">
                                {editingAdmin && (
                                    <button 
                                        type="button" 
                                        onClick={() => { setEditingAdmin(null); setFullName(''); setEmail(''); }} 
                                        className="flex-1 bg-white border-2 border-slate-200 p-4 rounded-2xl text-sm font-black hover:bg-slate-50 transition-all text-slate-400"
                                    >
                                        Annuler
                                    </button>
                                )}
                                <button 
                                    type="submit" 
                                    disabled={loading} 
                                    className="flex-1 bg-[#00a3eb] p-4 rounded-2xl text-sm font-black text-white hover:bg-[#0088cc] transition-all shadow-lg shadow-blue-200"
                                >
                                    {loading ? (
                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto"></div>
                                    ) : (
                                        editingAdmin ? 'Mettre à jour' : 'Enregistrer'
                                    )}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>

                {/* Users Table */}
                <div className="lg:col-span-8">
                    <div className="bg-white/60 backdrop-blur-xl border border-white p-8 rounded-[3rem] shadow-xl shadow-blue-100/50 h-full flex flex-col max-h-[700px]">
                        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
                            <h2 className="text-xl font-black flex items-center gap-3 text-[#00715d]">
                                <span className="p-2 bg-emerald-100 rounded-2xl">📂</span> Comptes Institutions
                            </h2>
                            <div className="relative w-full sm:w-64">
                                <input 
                                    type="text" 
                                    placeholder="Chercher..." 
                                    className="w-full bg-white border-2 border-[#9fdaf7]/30 rounded-2xl pl-10 pr-4 py-2 text-xs font-bold outline-none focus:border-[#00a3eb] transition-all" 
                                    value={searchTerm} 
                                    onChange={e => setSearchTerm(e.target.value)} 
                                />
                                <span className="absolute left-4 top-2.5 text-[#9fdaf7]">🔍</span>
                            </div>
                        </div>
                        <div className="overflow-x-auto flex-1 custom-scrollbar">
                            <table className="w-full text-left text-xs border-separate border-spacing-y-3">
                                <thead className="text-[#5b8a9f] font-black uppercase tracking-widest sticky top-0 bg-white/40 backdrop-blur-sm z-10">
                                    <tr>
                                        <th className="px-6 pb-2">Identité</th>
                                        <th className="px-6 pb-2">Email</th>
                                        <th className="px-6 pb-2 text-center">Effectif</th>
                                        <th className="px-6 pb-2 text-center">Ressources</th>
                                        <th className="px-6 pb-2 text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {isTableLoading ? (
                                        <tr><td colSpan="5" className="p-20 text-center font-bold text-[#b0c8d1] animate-pulse text-lg">Synchronisation des serveurs...</td></tr>
                                    ) : filteredAdmins.map(a => (
                                        <tr key={a.id} className="bg-white/80 hover:bg-white transition-all rounded-3xl group shadow-sm">
                                            <td className="px-6 py-4 rounded-l-3xl border-l-[6px] border-transparent group-hover:border-[#00a3eb]">
                                                <div className="font-black text-[#004d3e]">{a.fullName}</div>
                                                <div className="text-[10px] text-[#00a3eb] font-bold mt-0.5">{a.role === 'ADMIN' ? '🏛️ INSTITUTION' : '🎓 PROFESSEUR'}</div>
                                            </td>
                                            <td className="px-6 py-4 text-[#5b8a9f] font-bold">{a.email}</td>
                                            <td className="px-6 py-4 text-center">
                                                <span className="bg-blue-50 text-[#00a3eb] px-3 py-1 rounded-full font-black">
                                                    {globalStats[a.id]?.professorCount || 0}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-center">
                                                <span className="bg-emerald-50 text-[#00715d] px-3 py-1 rounded-full font-black">
                                                    {globalStats[a.id]?.documentCount || 0}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-right rounded-r-3xl">
                                                <button onClick={() => handleEdit(a)} className="bg-blue-50 text-[#00a3eb] w-8 h-8 rounded-xl hover:bg-[#00a3eb] hover:text-white transition-all font-bold">✎</button>
                                                <button onClick={() => handleDelete(a.id)} className="bg-rose-50 text-rose-500 w-8 h-8 rounded-xl hover:bg-rose-500 hover:text-white transition-all font-bold ml-2">🗑</button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            {/* --- MONGODB EXPLORER SECTION --- */}
            <div className="mt-12">
                <div className="bg-white/60 backdrop-blur-xl border border-white rounded-[3.5rem] p-10 shadow-2xl shadow-blue-100/50 overflow-hidden">
                    <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-10">
                        <div>
                            <h2 className="text-2xl font-black flex items-center gap-4 text-[#00715d]">
                                <span className="p-3 bg-emerald-100 rounded-[1.5rem] text-emerald-600 shadow-inner">📊</span>
                                Explorateur de Données <span className="text-[#5b8a9f] text-sm font-bold ml-2 italic">(Base IA - Lecture seule)</span>
                            </h2>
                            <p className="text-[#5b8a9f] text-sm font-medium mt-1">Inspection granulaire de la base MongoDB pour le diagnostic</p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            {collections.length === 0 ? (
                                <span className="text-[#b0c8d1] text-xs font-bold animate-pulse">Initialisation des collections...</span>
                            ) : collections.map(c => (
                                <button 
                                    key={c} 
                                    onClick={() => loadCollectionData(c)}
                                    className={`px-6 py-3 rounded-2xl text-xs font-black transition-all border-2 ${activeCollection === c ? 'bg-[#00a3eb] border-[#00a3eb] text-white shadow-lg shadow-blue-200' : 'bg-white border-[#9fdaf7]/20 text-[#5b8a9f] hover:border-[#00a3eb] hover:text-[#00a3eb] shadow-sm'}`}
                                >
                                    {c.toUpperCase()}
                                </button>
                            ))}
                        </div>
                    </div>

                    {activeCollection ? (
                        <div className="bg-white/80 rounded-[2.5rem] border-2 border-[#9fdaf7]/10 p-6 shadow-inner">
                            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4 px-2">
                                <div className="flex items-center gap-4">
                                    <span className="text-xs font-black text-[#00a3eb] tracking-widest uppercase px-4 py-2 bg-blue-50 rounded-xl border border-blue-100 shadow-sm">
                                        Collection: {activeCollection}
                                    </span>
                                    <span className="text-[11px] text-[#5b8a9f] font-bold">
                                        {collectionData.length} documents identifiés
                                    </span>
                                </div>
                                <div className="relative w-full sm:w-80">
                                    <input 
                                        type="text" 
                                        placeholder="Filtrer dans la collection..." 
                                        className="w-full bg-white border-2 border-[#9fdaf7]/30 rounded-2xl pl-12 pr-4 py-3 text-xs font-bold outline-none focus:border-[#00a3eb] transition-all shadow-sm" 
                                        value={mongoSearchTerm} 
                                        onChange={e => setMongoSearchTerm(e.target.value)} 
                                    />
                                    <span className="absolute left-4 top-3.5 text-[#9fdaf7]">🔎</span>
                                </div>
                            </div>
                            
                            {isMongoLoading ? (
                                <div className="py-24 flex flex-col items-center justify-center gap-6">
                                    <div className="w-12 h-12 border-4 border-[#00a3eb]/20 border-t-[#00a3eb] rounded-full animate-spin"></div>
                                    <p className="text-[#00a3eb] text-xs font-black tracking-widest animate-pulse">EXTRACTION DES DONNÉES EN COURS...</p>
                                </div>
                            ) : (
                                <div className="overflow-x-auto custom-scrollbar max-h-[600px] rounded-3xl border border-[#9fdaf7]/20 bg-white/50">
                                    <table className="w-full text-left border-collapse">
                                        <thead className="text-[#5b8a9f] sticky top-0 bg-[#f0fbff] backdrop-blur-md z-10">
                                            <tr>
                                                <th className="p-4 border-b border-[#9fdaf7]/10 font-black text-[10px] uppercase tracking-wider text-[#00a3eb] min-w-[140px] bg-blue-50/50">ID DOCUMENT</th>
                                                {(() => {
                                                    const filtered = collectionData.filter(doc => 
                                                        Object.values(doc).some(val => 
                                                            String(val).toLowerCase().includes(mongoSearchTerm.toLowerCase())
                                                        )
                                                    );
                                                    const allKeys = Array.from(new Set(filtered.flatMap(doc => Object.keys(doc))))
                                                        .filter(k => k !== '_id' && k !== '__v');
                                                    return allKeys.map(key => (
                                                        <th key={key} className="p-4 border-b border-[#9fdaf7]/10 font-black text-[10px] uppercase tracking-wider min-w-[180px]">{key}</th>
                                                    ));
                                                })()}
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-[#9fdaf7]/5">
                                            {(() => {
                                                const filtered = collectionData.filter(doc => 
                                                    Object.values(doc).some(val => 
                                                        String(val).toLowerCase().includes(mongoSearchTerm.toLowerCase())
                                                    )
                                                );
                                                
                                                if (filtered.length > 0) {
                                                    const allKeys = Array.from(new Set(filtered.flatMap(doc => Object.keys(doc))))
                                                        .filter(k => k !== '_id' && k !== '__v');
                                                        
                                                    return filtered.map((doc, idx) => (
                                                        <tr key={doc._id || idx} className="hover:bg-blue-50/50 transition-all group">
                                                            <td className="p-4 font-mono text-[#00a3eb] text-[9px] font-black align-top border-r border-[#9fdaf7]/10 bg-blue-50/20 group-hover:bg-blue-50/40">
                                                                {doc._id}
                                                            </td>
                                                            {allKeys.map(key => (
                                                                <td key={key} className="p-4 text-[#004d3e] text-[11px] font-bold align-top leading-relaxed group-hover:text-[#00a3eb]">
                                                                    {typeof doc[key] === 'object' && doc[key] !== null ? (
                                                                        <details className="cursor-pointer">
                                                                            <summary className="text-[#5b8a9f] font-black hover:text-[#00a3eb] focus:outline-none text-[10px] pb-1">OBJET DYNAMIQUE ({Object.keys(doc[key] || {}).length} éléments)</summary>
                                                                            <pre className="mt-3 text-[10px] bg-slate-50 p-4 rounded-2xl border-2 border-blue-50 overflow-x-auto font-mono text-[#00715d] leading-normal shadow-inner">
                                                                                {JSON.stringify(doc[key], null, 2)}
                                                                            </pre>
                                                                        </details>
                                                                    ) : (
                                                                        <span className="line-clamp-4">{String(doc[key] ?? '')}</span>
                                                                    )}
                                                                </td>
                                                            ))}
                                                        </tr>
                                                    ));
                                                } else {
                                                    return (
                                                        <tr>
                                                            <td colSpan="100" className="py-24 text-center text-[#b0c8d1] flex flex-col items-center gap-4">
                                                                <span className="text-4xl filter grayscale opacity-50">🔍</span>
                                                                <span className="font-black tracking-widest">{mongoSearchTerm ? `AUCUN RÉSULTAT POUR "${mongoSearchTerm.toUpperCase()}"` : "CETTE COLLECTION EST VIDE"}</span>
                                                            </td>
                                                        </tr>
                                                    );
                                                }
                                            })()}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="py-24 border-4 border-dashed border-[#9fdaf7]/20 rounded-[3rem] flex flex-col items-center justify-center bg-[#f0fbff]/30">
                            <div className="w-20 h-20 bg-white rounded-[2rem] shadow-xl shadow-blue-100 flex items-center justify-center text-3xl mb-6 text-[#9fdaf7] animate-bounce">🔍</div>
                             <p className="text-[#00715d] font-black text-lg tracking-tight">SÉLECTIONNEZ UNE COLLECTION POUR COMMENCER L'ANALYSE</p>
                             <p className="text-[#5b8a9f] text-xs font-bold mt-2 uppercase tracking-widest">Inspection en lecture seule de l'infrastructure persistante</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Starter;
