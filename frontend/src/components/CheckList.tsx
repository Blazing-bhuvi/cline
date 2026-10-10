import type { CheckItem } from "../types";
import { StatusBadge } from "./StatusBadge";

export function CheckList({ items }: { items: CheckItem[] }) {
  return (
    <ul className="divide-y divide-slate-200">
      {items.map((it) => (
        <li key={it.key} className="py-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-800">{it.label}</span>
            <StatusBadge status={it.status} />
          </div>
          {it.reason && <p className="mt-1 text-sm text-slate-600">{it.reason}</p>}
        </li>
      ))}
    </ul>
  );
}
