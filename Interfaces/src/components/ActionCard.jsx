export const ActionCard = ({ title, children, icon }) => (
    <div className="glass-effect rounded-2xl p-6 hover:border-indigo-500/50 transition-all shadow-xl">
        <div className="flex items-center gap-3 mb-4 border-b border-white/5 pb-3">
            {icon && <span className="text-indigo-400">{icon}</span>}
            <h2 className="text-indigo-400 font-semibold text-sm uppercase tracking-widest">
                {title}
            </h2>
        </div>
        {children}
    </div>
);