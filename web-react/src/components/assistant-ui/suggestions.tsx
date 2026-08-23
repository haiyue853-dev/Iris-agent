export function Suggestions({ items, onSelect }: { items: string[]; onSelect: (value: string) => void }) {
  return (
    <div className="iris-suggestions" aria-label="快捷建议">
      {items.map((item) => <button type="button" key={item} onClick={() => onSelect(item)}>{item}</button>)}
    </div>
  );
}
