// Sprungleiste im Kopf der Instrumentseite: alle Bereiche (Chart, Muster, Prognose, ...) mit einem Tipp erreichbar.
// Die Zähler stammen aus den bereits geladenen Analysen; fehlt eine Zahl, wird keine angezeigt (kein Ersatzwert).
export interface SectionItem { id: string; label: string; count?: number }

export function SectionNav({ items }: { items: SectionItem[] }) {
  const go = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };
  return (
    <nav aria-label="Bereiche dieser Seite" className="sticky top-[53px] z-20 -mx-4 mb-3 border-b border-slate-800 bg-slate-950/95 px-4 py-2 backdrop-blur">
      <ul className="flex gap-2 overflow-x-auto">
        {items.map((i) => (
          <li key={i.id} className="shrink-0">
            <button type="button" onClick={() => go(i.id)} className="seg">
              {i.label}
              {i.count != null && <span className="ml-1.5 rounded-full bg-slate-800 px-1.5 text-xs text-slate-300">{i.count}</span>}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
