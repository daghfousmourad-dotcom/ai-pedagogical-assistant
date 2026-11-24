import React from 'react';

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3000';

export default function MLOpsMonitoring() {
    return (
        <div className="h-screen bg-[#f0fbff] flex flex-col overflow-hidden font-sans">
            <header className="bg-white/60 backdrop-blur-md border-b border-[#9fdaf7]/30 p-6 flex justify-between items-center shrink-0 shadow-sm">
                <div className="flex items-center gap-6">
                    <button 
                        onClick={() => window.location.href = '/mlops-admin'}
                        className="bg-white hover:bg-[#f0fbff] text-[#00a3eb] px-6 py-2.5 rounded-2xl transition-all border border-[#9fdaf7]/30 font-black flex items-center gap-2 shadow-sm"
                    >
                        <span>←</span> Console MLOps
                    </button>
                    <div className="h-8 w-px bg-[#9fdaf7]/30 mx-2"></div>
                    <h1 className="text-2xl font-black text-[#004d3e] flex items-center gap-4 tracking-tight">
                        <span className="w-4 h-4 rounded-full bg-emerald-500 animate-pulse shadow-lg shadow-emerald-200"></span>
                        Supervision Flux Systèmes <span className="text-[#00a3eb] text-sm font-bold uppercase tracking-widest ml-2">Live Monitoring</span>
                    </h1>
                </div>
                <div className="flex gap-4">
                    <a 
                        href={GRAFANA_URL} 
                        target="_blank" 
                        rel="noreferrer" 
                        className="bg-[#00a3eb] hover:bg-[#0088cc] text-white px-8 py-2.5 rounded-2xl transition-all font-black shadow-lg shadow-blue-100 flex items-center gap-2"
                    >
                        <span>🚀</span> Ouvrir Grafana Expert
                    </a>
                </div>
            </header>
            
            <main className="flex-1 w-full h-full overflow-hidden bg-white">
                <iframe 
                    src={`${GRAFANA_URL}/d/mlops-dashboard?orgId=1&refresh=5s&kiosk`} 
                    className="w-full h-full border-0 opacity-90 hover:opacity-100 transition-opacity"
                    title="Grafana Dashboard Full"
                ></iframe>
            </main>
        </div>
    );
}
