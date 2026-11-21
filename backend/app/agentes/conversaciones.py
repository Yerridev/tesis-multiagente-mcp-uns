"""Registro de chats con los agentes.

Cada conversación se guarda como un archivo JSON: sirve de evidencia para la
tesis (qué se preguntó, qué respondió, con qué modelo y en cuánto tiempo).

Port de ``ConversacionesStore.cs``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class ConversacionesStore:
    def __init__(self, ruta: str | None = None) -> None:
        self.dir = Path(ruta) if ruta else (Path.cwd() / "registros" / "conversaciones")
        self._lock = threading.RLock()   # reentrante: registrar() llama a leer() con el lock tomado
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:                 # pragma: no cover
            log.warning("Sin disco para las conversaciones: %s", exc)

    def _ruta(self, id_: str) -> Path:
        return self.dir / f"{id_}.json"

    # ------------------------------------------------------------------ lectura
    def leer(self, id_: str) -> dict[str, Any] | None:
        if not ID_VALIDO.match(id_ or ""):
            return None
        with self._lock:
            archivo = self._ruta(id_)
            if not archivo.is_file():
                return None
            try:
                return json.loads(archivo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None

    def listar(self, usuario: str | None = None, maximo: int = 200) -> list[dict[str, Any]]:
        """``usuario=None`` devuelve todas; si no, solo las de ese usuario."""
        with self._lock:
            if not self.dir.is_dir():
                return []
            archivos = sorted(self.dir.glob("*.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)[:maximo]
            resumen: list[dict[str, Any]] = []
            for archivo in archivos:
                try:
                    conv = json.loads(archivo.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if usuario is not None and conv.get("usuario") != usuario:
                    continue
                mensajes = conv.get("mensajes") or []
                modelos = sorted({m["modelo"] for m in mensajes if m.get("modelo")})
                resumen.append({
                    "id": conv.get("id", ""),
                    "origen": conv.get("origen", "agentes"),
                    "usuario": conv.get("usuario"),
                    "titulo": conv.get("titulo", ""),
                    "creada": conv.get("creada"),
                    "actualizada": conv.get("actualizada"),
                    "mensajes": len(mensajes),
                    "modelos": modelos,
                })
            return resumen

    # ------------------------------------------------------------------ escritura
    def registrar(self, id_: str | None, origen: str | None, pregunta: str,
                  respuesta: dict[str, Any], usuario: str | None = None) -> str:
        """Agrega la pregunta y la respuesta; crea la conversación si no existe."""
        with self._lock:
            conv = (self.leer(id_) if id_ and ID_VALIDO.match(id_) else None)
            if conv is None:
                ahora = datetime.now().astimezone()
                conv = {
                    "id": f"{ahora:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
                    "origen": (origen or "agentes").strip()[:40],
                    "usuario": usuario,
                    "titulo": (pregunta[:70] + "…") if len(pregunta) > 70 else pregunta,
                    "creada": ahora.isoformat(),
                    "actualizada": ahora.isoformat(),
                    "mensajes": [],
                }
            ahora = datetime.now().astimezone()
            herramientas = respuesta.get("tools") or []
            consulta = next((t for t in herramientas if t.get("name") == "consulta_openrouter"), None)
            conv["mensajes"].append({"rol": "user", "texto": pregunta, "ts": ahora.isoformat()})
            conv["mensajes"].append({
                "rol": "agente",
                "texto": respuesta.get("reply", ""),
                "ts": respuesta.get("ts") or ahora.isoformat(),
                "modelo": respuesta.get("model"),
                "modo": respuesta.get("mode"),
                "herramientas": herramientas,
                "ms": consulta.get("ms") if consulta else None,
            })
            conv["actualizada"] = ahora.isoformat()
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                self._ruta(conv["id"]).write_text(
                    json.dumps(conv, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            except OSError as exc:              # pragma: no cover
                # El chat sigue funcionando aunque no se pueda guardar.
                log.warning("No se pudo guardar la conversación: %s", exc)
            return conv["id"]
