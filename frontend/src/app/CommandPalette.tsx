import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator, CommandShortcut } from '@/components/ui/command';

export function CommandPalette({ nav, onClose }: { nav: Array<{ to: string; label: string }>; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  function go(path: string) { navigate(path); onClose(); }
  return <CommandDialog open onOpenChange={open => { if (!open) onClose(); }} title="Tìm kiếm nhanh" description="Tìm gói thầu hoặc mở khu vực làm việc" className="sm:max-w-xl">
    <Command><CommandInput autoFocus placeholder="Tìm mã, tên gói hoặc lệnh…" value={query} onValueChange={setQuery}/>
      <CommandList><CommandEmpty>Không có lệnh phù hợp.</CommandEmpty>
        <CommandGroup heading="Đi tới">{nav.map(item => <CommandItem key={item.to} value={item.label} onSelect={() => go(item.to)}>{item.label}<CommandShortcut>↵</CommandShortcut></CommandItem>)}</CommandGroup>
        {query.trim() && <><CommandSeparator/><CommandGroup heading="Tra cứu"><CommandItem value={`Tra cứu ${query}`} onSelect={() => go('/app/search?q=' + encodeURIComponent(query) + '&run=1')}>Tra cứu “{query}”<CommandShortcut>↵</CommandShortcut></CommandItem></CommandGroup></>}
      </CommandList></Command>
  </CommandDialog>;
}
