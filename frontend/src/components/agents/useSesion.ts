import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react';

/**
 * useState que sobrevive a cambiar de módulo y a refrescar (sessionStorage de la pestaña).
 * Se pierde solo al cerrar el navegador/pestaña (apagar todo) o cuando el código lo limpia (Nuevo chat).
 */
export function useSesion<T>(clave: string, inicial: T): [T, (v: SetStateAction<T>) => void] {
  const leer = (): T => {
    try {
      const crudo = sessionStorage.getItem(clave);
      return crudo ? (JSON.parse(crudo) as T) : inicial;
    } catch {
      return inicial;
    }
  };
  const [valor, setValor] = useState<T>(leer);
  const claveRef = useRef(clave);
  useEffect(() => {
    if (claveRef.current !== clave) { claveRef.current = clave; setValor(leer()); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave]);
  useEffect(() => {
    try { sessionStorage.setItem(clave, JSON.stringify(valor)); } catch { /* sin almacenamiento */ }
  }, [clave, valor]);
  const set = useCallback((v: SetStateAction<T>) => setValor(v), []);
  return [valor, set];
}
