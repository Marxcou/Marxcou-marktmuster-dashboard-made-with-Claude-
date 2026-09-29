export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <h1 className="mb-2">{title}</h1>
      <p className="text-slate-400">{note}</p>
    </section>
  );
}
