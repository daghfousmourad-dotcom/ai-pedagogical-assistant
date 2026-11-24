import React, { useState, useEffect } from 'react';

const FASTAPI_URL = import.meta.env.VITE_FASTAPI_URL || 'http://localhost:5005';
const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3000';

const TEXT_MODELS = [
    { id: 'colbert-ir/colbertv2.0', label: 'ColBERT v2.0 (Expert RAG)' },
    { id: 'Qwen/Qwen3-Embedding-8B', label: 'Qwen3 Embedding (MTEB Leader - FP16 16GB)' },
    { id: 'Qwen/Qwen3-Embedding-8B-Int4', label: 'Qwen3 Embedding (Allégé - Int4 5GB)' },
    { id: 'snowflake/snowflake-arctic-embed-m', label: 'Snowflake Arctic (M)' },
    { id: 'BAAI/bge-small-en-v1.5', label: 'BGE Small v1.5' },
    { id: 'jinaai/jina-embeddings-v2-base-en', label: 'Jina v2 Base' },
    { id: 'sentence-transformers/all-MiniLM-L6-v2', label: 'MiniLM-L6 (Léger)' }
];

const VISION_CUDA_MODELS = [
    { id: 'vidore/colqwen3.5', label: 'ColQwen 3.5 (SOTA - FP16)' },
    { id: 'vidore/colqwen3.5-Int4', label: 'ColQwen 3.5 (Allégé - Int4)' },
    { id: 'hydra-vlm/hydra-4b', label: 'Hydra 4B (Unified VDR - ~5GB)' },
    { id: 'vidore/colpali-v1.3', label: 'ColPali v1.3 (SOTA)' },
    { id: 'vidore/colpali-v1.2', label: 'ColPali v1.2' },
    { id: 'vidore/colpali-v1.1', label: 'ColPali v1.1' }
];

const VISION_CPU_MODELS = [
    { id: 'vidore/colSmol-256M', label: 'ColSmol 256M (CPU Optimal)' },
    { id: 'vidore/colSmol-125M', label: 'ColSmol 125M (Ultra Rapide)' },
    { id: 'vidore/colIdefics3-8B-Small', label: 'Idefics3 8B (Qualité CPU)' }
];

const LLM_PROVIDERS = [
    { id: 'OPENAI', label: 'OpenAI (Cloud)' },
    { id: 'OLLAMA', label: 'Ollama (Local)' },
    { id: 'GEMINI', label: 'Google Gemini (Cloud)' }
];

const OPENAI_MODELS = ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'];
const OLLAMA_MODELS = ['qwen2.5:7b', 'llama3.1:8b', 'mistral', 'phi3'];
const GEMINI_MODELS = ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'];

export default function MLOpsDashboard() {
    const [versions, setVersions] = useState([]);
    const [llmConfigs, setLlmConfigs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [restartingAI, setRestartingAI] = useState(false);
    const [restartingFull, setRestartingFull] = useState(false);

    const [newVersion, setNewVersion] = useState({
        version_name: '',
        text_model: 'colbert-ir/colbertv2.0',
        vision_model_cuda: 'vidore/colpali-v1.3',
        vision_model_cpu: 'vidore/colSmol-256M',
        extraction_method: 'pymupdf_blocks',
        qdrant_collection: 'Vector_Embeddings',
        text_block_threshold: 15
    });

    const [newLLM, setNewLLM] = useState({
        config_name: '',
        llm_provider: 'OPENAI',
        llm_model: 'gpt-4o-mini',
        llm_temperature: 0.7,
        llm_max_tokens: 500,
        llm_top_p: 1.0,
        llm_frequency_penalty: 0.0,
        llm_presence_penalty: 0.0,
        stt_provider: 'OPENAI',
        tts_provider: 'OPENAI'
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [resV, resL] = await Promise.all([
                fetch(`${FASTAPI_URL}/api/admin/mlops/versions`),
                fetch(`${FASTAPI_URL}/api/admin/mlops/llm-configs`)
            ]);
            const dataV = await resV.json();
            const dataL = await resL.json();
            
            if (dataV.status === 'success') {
                setVersions(dataV.versions.sort((a, b) => (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0)));
            }
            if (dataL.status === 'success') {
                setLlmConfigs(dataL.configs.sort((a, b) => (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0)));
            }
        } catch (e) {
            console.error("Erreur MLOps", e);
        } finally {
            setLoading(false);
        }
    };

    // --- PIPELINES VECTORIELS ---
    const handleCreateVersion = async (e) => {
        e.preventDefault();
        try {
            const res = await fetch(`${FASTAPI_URL}/api/admin/mlops/versions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newVersion)
            });
            const data = await res.json();
            if (data.status === 'success') {
                setNewVersion({ ...newVersion, version_name: '' });
                fetchData();
            } else {
                alert(data.detail || "Erreur lors de la création");
            }
        } catch (e) { console.error(e); }
    };

    const activateVersion = async (name) => {
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/versions/${name}/activate`, { method: 'PUT' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    const setDefaultVersion = async (name) => {
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/versions/${name}/default`, { method: 'PUT' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    const deleteVersion = async (name) => {
        if (!window.confirm(`Supprimer la config vectorielle "${name}" ?`)) return;
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/versions/${name}`, { method: 'DELETE' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    // --- CONFIGS LLM ---
    const handleCreateLLM = async (e) => {
        e.preventDefault();
        try {
            const res = await fetch(`${FASTAPI_URL}/api/admin/mlops/llm-configs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newLLM)
            });
            const data = await res.json();
            if (data.status === 'success') {
                setNewLLM({ ...newLLM, config_name: '' });
                fetchData();
            } else {
                alert(data.detail || "Erreur lors de la création LLM");
            }
        } catch (e) { console.error(e); }
    };

    const activateLLM = async (name) => {
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/llm-configs/${name}/activate`, { method: 'PUT' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    const setDefaultLLM = async (name) => {
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/llm-configs/${name}/default`, { method: 'PUT' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    const deleteLLM = async (name) => {
        if (!window.confirm(`Supprimer la config LLM "${name}" ?`)) return;
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/llm-configs/${name}`, { method: 'DELETE' });
            fetchData();
        } catch (e) { console.error(e); }
    };

    // --- REBOOT ---
    const handleRestartAI = async () => {
        if (!window.confirm("Redémarrer uniquement les services IA ?")) return;
        setRestartingAI(true);
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/system/restart`, { method: 'POST' });
            setTimeout(() => { setRestartingAI(false); window.location.reload(); }, 5000);
        } catch (e) { alert("Erreur reboot IA"); setRestartingAI(false); }
    };

    const handleRestartFull = async () => {
        if (!window.confirm("ATTENTION : Redémarrer TOUT le système ?")) return;
        setRestartingFull(true);
        try {
            await fetch(`${FASTAPI_URL}/api/admin/mlops/system/restart-full`, { method: 'POST' });
            setTimeout(() => { setRestartingFull(false); window.location.reload(); }, 10000);
        } catch (e) { alert("Erreur reboot global"); setRestartingFull(false); }
    };

    const activeVersion = versions.find(v => v.is_active);
    const activeLLM = llmConfigs.find(v => v.is_active);

    return (
        <div className="min-h-screen bg-gradient-to-br from-[#f0fbff] via-[#bae6fd] to-[#7dd3fc] p-6 md:p-12 font-sans text-[#004d3e]">
            <header className="mb-10 flex flex-col md:flex-row items-start md:items-center justify-between bg-white/40 backdrop-blur-md p-8 rounded-[3rem] border border-white/50 shadow-sm gap-6">
                <div>
                    <h1 className="text-4xl font-black bg-gradient-to-r from-[#00a3eb] to-[#00715d] bg-clip-text text-transparent tracking-tight">AI Assistant <span className="text-[#00a3eb]">MLOps</span></h1>
                    <p className="text-[#5b8a9f] mt-1 font-bold uppercase tracking-widest text-xs">Gestion séparée Vectors & LLM</p>
                </div>
                <div className="flex flex-wrap gap-3">
                    <button onClick={handleRestartAI} disabled={restartingAI || restartingFull} className={`${restartingAI ? 'bg-amber-400' : 'bg-[#00a3eb] hover:bg-[#0088cc]'} text-white px-6 py-2.5 rounded-2xl transition shadow-lg font-black`}>
                        {restartingAI ? 'Redémarrage...' : 'Reboot IA'}
                    </button>
                    <button onClick={handleRestartFull} disabled={restartingAI || restartingFull} className={`${restartingFull ? 'bg-amber-400' : 'bg-[#f1416c] hover:bg-[#d9214e]'} text-white px-6 py-2.5 rounded-2xl transition shadow-lg font-black`}>
                        {restartingFull ? 'Reboot Global...' : 'Full System Restart'}
                    </button>
                    <button onClick={() => window.location.href='/starter.html'} className="bg-white/60 text-[#5b8a9f] px-6 py-2.5 rounded-2xl hover:bg-white transition font-black border border-white/50 shadow-sm">Quitter</button>
                </div>
            </header>
            
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mb-8">
                
                {/* SECTION 1: EMBEDDINGS & VISION */}
                <div className="space-y-8">
                    <div className="bg-white/60 backdrop-blur-xl p-8 rounded-[3rem] border border-white relative overflow-hidden shadow-xl shadow-blue-100/50">
                        <div className="absolute top-0 left-0 w-2 h-full bg-gradient-to-b from-[#00a3eb] to-[#9fdaf7]"></div>
                        <h2 className="text-xl font-black mb-8 text-[#00a3eb] flex items-center gap-3">
                            <span className="p-2 bg-blue-100 rounded-2xl">🔍</span> Pipeline Vecteurs & Vision
                        </h2>
                        
                        <form onSubmit={handleCreateVersion} className="space-y-6">
                            <div>
                                <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Nom du Pipeline</label>
                                <input type="text" required value={newVersion.version_name} onChange={e => setNewVersion({...newVersion, version_name: e.target.value})} className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-4 text-sm font-bold outline-none focus:border-[#00a3eb]" placeholder="Ex: RAG_ColPali_v1" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Modèle Texte</label>
                                    <select value={newVersion.text_model} onChange={e => setNewVersion({...newVersion, text_model: e.target.value})} className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-3 text-xs font-black">
                                        {TEXT_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Vision (GPU)</label>
                                    <select value={newVersion.vision_model_cuda} onChange={e => setNewVersion({...newVersion, vision_model_cuda: e.target.value})} className="w-full bg-white/80 border-2 border-[#9fdaf7]/30 rounded-2xl p-3 text-xs font-black">
                                        {VISION_CUDA_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
                                    </select>
                                </div>
                            </div>
                            <button type="submit" className="w-full bg-[#00a3eb] hover:bg-[#0088cc] text-white font-black py-3 rounded-[1.5rem] mt-4 shadow-md">Créer Pipeline Vectoriel</button>
                        </form>

                        <div className="mt-8 space-y-3 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
                            {versions.map(v => (
                                <div key={v.version_name} className={`p-4 rounded-2xl border-2 ${v.is_active ? 'border-[#00a3eb] bg-white' : 'border-white bg-white/40'} flex justify-between items-center transition-all`}>
                                    <div>
                                        <div className="flex gap-2 items-center">
                                            <span className="font-black text-[#004d3e] text-sm">{v.version_name}</span>
                                            {v.is_active && <span className="bg-[#00a3eb] text-white text-[9px] px-2 py-0.5 rounded-full font-bold">Actif</span>}
                                        </div>
                                        <div className="text-[10px] text-[#5b8a9f] font-bold mt-1">{v.text_model.split('/').pop()} | {v.vision_model_cuda.split('/').pop()}</div>
                                    </div>
                                    <div className="flex gap-2">
                                        {!v.is_active && <button onClick={() => activateVersion(v.version_name)} className="bg-[#00a3eb] text-white px-3 py-1.5 rounded-xl text-xs font-bold hover:bg-[#0088cc]">Activer</button>}
                                        {!v.is_active && <button onClick={() => deleteVersion(v.version_name)} className="text-rose-500 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-xl hover:bg-rose-500 hover:text-white transition-all text-xs">🗑</button>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* SECTION 2: LLMs */}
                <div className="space-y-8">
                    <div className="bg-white/60 backdrop-blur-xl p-8 rounded-[3rem] border border-white relative overflow-hidden shadow-xl shadow-emerald-100/50">
                        <div className="absolute top-0 left-0 w-2 h-full bg-gradient-to-b from-[#00715d] to-[#6ee7b7]"></div>
                        <h2 className="text-xl font-black mb-8 text-[#00715d] flex items-center gap-3">
                            <span className="p-2 bg-emerald-100 rounded-2xl">🧠</span> Moteurs de Raisonnement LLM
                        </h2>
                        
                        <form onSubmit={handleCreateLLM} className="space-y-6">
                            <div>
                                <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Nom de Config LLM</label>
                                <input type="text" required value={newLLM.config_name} onChange={e => setNewLLM({...newLLM, config_name: e.target.value})} className="w-full bg-white/80 border-2 border-[#6ee7b7]/30 rounded-2xl p-4 text-sm font-bold outline-none focus:border-[#00715d]" placeholder="Ex: Local_Ollama_Llama3" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Fournisseur</label>
                                    <select value={newLLM.llm_provider} onChange={e => {
                                        const p = e.target.value;
                                        setNewLLM({...newLLM, llm_provider: p, llm_model: p==='OLLAMA'?'llama3.1:8b':p==='GEMINI'?'gemini-2.0-flash':'gpt-4o-mini'});
                                    }} className="w-full bg-white/80 border-2 border-[#6ee7b7]/30 rounded-2xl p-3 text-xs font-black">
                                        {LLM_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Modèle LLM</label>
                                    <select value={newLLM.llm_model} onChange={e => setNewLLM({...newLLM, llm_model: e.target.value})} className="w-full bg-white/80 border-2 border-[#6ee7b7]/30 rounded-2xl p-3 text-xs font-black">
                                        {(newLLM.llm_provider === 'OPENAI' ? OPENAI_MODELS : newLLM.llm_provider === 'GEMINI' ? GEMINI_MODELS : OLLAMA_MODELS).map(m => <option key={m} value={m}>{m}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Temp ({newLLM.llm_temperature})</label>
                                    <input type="range" min="0" max="2" step="0.1" value={newLLM.llm_temperature} onChange={e => setNewLLM({...newLLM, llm_temperature: parseFloat(e.target.value)})} className="w-full h-2 rounded-lg accent-[#00715d] bg-emerald-100" />
                                </div>
                                <div>
                                    <label className="text-[10px] font-black text-[#5b8a9f] uppercase mb-2 ml-2 block">Max Tokens</label>
                                    <input type="number" value={newLLM.llm_max_tokens} onChange={e => setNewLLM({...newLLM, llm_max_tokens: parseInt(e.target.value)})} className="w-full bg-white/80 border-2 border-[#6ee7b7]/30 rounded-2xl p-3 text-xs font-black focus:border-[#00715d] outline-none" />
                                </div>
                            </div>
                            <button type="submit" className="w-full bg-[#00715d] hover:bg-[#005748] text-white font-black py-3 rounded-[1.5rem] mt-4 shadow-md">Déployer Config LLM</button>
                        </form>

                        <div className="mt-8 space-y-3 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
                            {llmConfigs.map(c => (
                                <div key={c.config_name} className={`p-4 rounded-2xl border-2 ${c.is_active ? 'border-[#00715d] bg-white' : 'border-white bg-white/40'} flex justify-between items-center transition-all`}>
                                    <div>
                                        <div className="flex gap-2 items-center">
                                            <span className="font-black text-[#004d3e] text-sm">{c.config_name}</span>
                                            {c.is_active && <span className="bg-[#00715d] text-white text-[9px] px-2 py-0.5 rounded-full font-bold">Actif</span>}
                                        </div>
                                        <div className="text-[10px] text-[#5b8a9f] font-bold mt-1">{c.llm_provider} | {c.llm_model} | Temp: {c.llm_temperature}</div>
                                    </div>
                                    <div className="flex gap-2">
                                        {!c.is_active && <button onClick={() => activateLLM(c.config_name)} className="bg-[#00715d] text-white px-3 py-1.5 rounded-xl text-xs font-bold hover:bg-[#005748]">Activer</button>}
                                        {!c.is_active && <button onClick={() => deleteLLM(c.config_name)} className="text-rose-500 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-xl hover:bg-rose-500 hover:text-white transition-all text-xs">🗑</button>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* ETAT LIVE */}
            <div className="bg-white/40 backdrop-blur-3xl rounded-[3rem] p-8 border border-white flex flex-col md:flex-row gap-6 justify-between items-center shadow-lg">
                <div className="flex items-center gap-4">
                    <span className="p-4 bg-emerald-100 rounded-[1.5rem] text-emerald-600 text-3xl shadow-inner">🟢</span>
                    <div>
                        <h3 className="text-2xl font-black text-[#00715d]">État Global Live</h3>
                        <p className="text-xs font-bold text-[#5b8a9f]">Synchronisation en temps réel avec le Backend FastAPI</p>
                    </div>
                </div>
                <div className="flex flex-col sm:flex-row gap-8 bg-white/60 p-6 rounded-3xl border border-white">
                    <div>
                        <span className="text-[10px] font-black text-[#5b8a9f] uppercase block mb-2 tracking-widest">Vecteurs & Vision</span>
                        <span className="text-xl font-black text-[#00a3eb]">{activeVersion ? activeVersion.version_name : "Aucun"}</span>
                    </div>
                    <div className="w-full sm:w-px h-px sm:h-auto bg-blue-100"></div>
                    <div>
                        <span className="text-[10px] font-black text-[#5b8a9f] uppercase block mb-2 tracking-widest">Cerveau LLM</span>
                        <span className="text-xl font-black text-[#00715d]">{activeLLM ? activeLLM.config_name : "Aucun"}</span>
                    </div>
                </div>
            </div>

        </div>
    );
}
