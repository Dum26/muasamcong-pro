import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';

const ConfirmContext = createContext<((message: string) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const resolver = useRef<((accepted: boolean) => void) | null>(null);
  useEffect(() => () => { resolver.current?.(false); resolver.current = null; }, []);
  const settle = useCallback((accepted: boolean) => { resolver.current?.(accepted); resolver.current = null; setMessage(null); }, []);
  const confirmAction = useCallback((text: string) => {
    resolver.current?.(false);
    setMessage(text);
    return new Promise<boolean>(resolve => { resolver.current = resolve; });
  }, []);
  return <ConfirmContext.Provider value={confirmAction}>{children}
    <AlertDialog open={message !== null} onOpenChange={open => { if (!open) settle(false); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Xác nhận thao tác</AlertDialogTitle><AlertDialogDescription>{message}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel onClick={() => settle(false)}>Hủy</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={() => settle(true)}>Xác nhận</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </ConfirmContext.Provider>;
}

export function useConfirm() {
  const confirmAction = useContext(ConfirmContext);
  if (!confirmAction) throw new Error('ConfirmProvider is missing');
  return confirmAction;
}
