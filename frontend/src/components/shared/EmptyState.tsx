import { Inbox, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export function EmptyState({ title, description, action, icon: Icon = Inbox }: { title: string; description?: string; action?: ReactNode; icon?: LucideIcon }) {
  return <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border bg-muted/20 p-8 text-center"><Icon className="size-6 text-muted-foreground" aria-hidden="true"/><strong>{title}</strong>{description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}{action}</div>;
}
