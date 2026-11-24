export const StatBadge = ({ label, value, color }) => (
    <div className="bg-slate-800/50 p-4 rounded-xl border border-white/10 text-center">
        <div className={`text-xl font-bold ${color}`}>{value}</div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mt-1">{label}</div>
    </div>
);