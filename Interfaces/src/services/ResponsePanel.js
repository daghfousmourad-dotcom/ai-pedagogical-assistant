const ResponsePanel = ({ data }) => {
    if (!data) return (
        <div className="mt-10 p-6 bg-black/40 border-l-4 border-indigo-500 rounded-xl text-slate-500 italic">
            // En attente d'une action...
        </div>
    );

    const renderContent = () => {
        const list = data.success ? data.data : data;

        if (Array.isArray(list)) {
            if (list.length === 0) return "Aucun résultat trouvé.";

            const keys = Object.keys(list[0]).filter(k => k !== 'password_hash');

            return (
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="border-b border-white/10 text-indigo-400 text-[10px] uppercase tracking-wider">
                        <tr>
                            {keys.map(k => <th key={k} className="p-3">{k}</th>)}
                        </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                        {list.map((item, i) => (
                            <tr key={i} className="hover:bg-white/5 transition">
                                {keys.map(k => (
                                    <td key={k} className="p-3 font-mono text-xs">
                                        {typeof item[k] === 'boolean' ? (item[k] ? '✅' : '❌') : String(item[k] || '--')}
                                    </td>
                                ))}
                            </tr>
                        ))}
                        </tbody>
                    </table>
                </div>
            );
        }

        return <pre className="text-xs text-green-400">{JSON.stringify(data, null, 2)}</pre>;
    };

    return (
        <div className="mt-10 p-6 bg-black/40 border-l-4 border-indigo-500 rounded-xl max-h-[600px] overflow-auto">
            {renderContent()}
        </div>
    );
};