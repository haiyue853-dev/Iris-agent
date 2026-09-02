export function FollowUpSuggestions({ items }: { items: string[] }) {
  if (!items.length) return null;
  return <section className="iris-follow-up-suggestions" aria-label="继续追问">
    <span>继续追问</span>
    <div>{items.map((item) => <button key={item} type="button" onClick={() => window.dispatchEvent(new CustomEvent("iris:use-follow-up", { detail: { text: item } }))}>{item}</button>)}</div>
  </section>;
}
