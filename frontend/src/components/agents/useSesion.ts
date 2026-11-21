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
  // Escribe en sessionStorage AL INSTANTE (no en un efecto): si la página se desmonta mientras
  // espera una respuesta (el usuario cambió de módulo), la respuesta igual queda guardada.
  // Las actualizaciones funcionales parten de lo guardado, que siempre es lo más reciente.
  const set = useCallback((v: SetStateAction<T>) => {
    let previo: T = inicial;
    try { const crudo = sessionStorage.getItem(claveRef.current); previo = crudo ? (JSON.parse(crudo) as T) : inicial; } catch { /* sin almacenamiento */ }
    const nuevo = typeof v === 'function' ? (v as (p: T) => T)(previo) : v;
    try { sessionStorage.setItem(claveRef.current, JSON.stringify(nuevo)); } catch { /* sin almacenamiento */ }
    setValor(nuevo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return [valor, set];
}
