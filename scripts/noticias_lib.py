# -*- coding: utf-8 -*-
"""Piezas compartidas de la seccion Actualidad.

Las usan el respaldo automatico (noticias_rss.py), las pruebas
(probar_noticias.py) y, a mano, el comando /noticia-del-dia cuando toca
guardar. Todo con biblioteca estandar: el Action no instala nada.

Las tres reglas que importan y que aqui se hacen cumplir:
  · nunca mas de 3 noticias, y la que sobra es siempre la mas antigua;
  · nunca una url repetida ni un dominio fuera de la lista blanca;
  · nunca un JSON que no cuadre con config/esquema_noticias.json.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import unicodedata
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_NOTICIAS = os.path.join(RAIZ, "data", "noticias.json")
RUTA_FUENTES = os.path.join(RAIZ, "config", "fuentes.json")
RUTA_PALABRAS = os.path.join(RAIZ, "config", "palabras_clave.json")
RUTA_ESQUEMA = os.path.join(RAIZ, "config", "esquema_noticias.json")
RUTA_LOG = os.path.join(RAIZ, "logs", "noticias.log")

AGENTE = "ILR-NoticiasBot/1.0 (+https://consultorciberdocchile-spec.github.io/)"


class Rechazo(Exception):
    """Algo no cumple una regla. Lleva el motivo en texto, para el log."""


# ── Archivos ────────────────────────────────────────────────────────────────
def leer_json(ruta, por_defecto=None):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if por_defecto is None:
            raise
        return por_defecto


def cargar_config():
    return leer_json(RUTA_FUENTES), leer_json(RUTA_PALABRAS), leer_json(RUTA_ESQUEMA)


def cargar_noticias(ruta=None):
    datos = leer_json(ruta or RUTA_NOTICIAS, [])
    if not isinstance(datos, list):
        raise Rechazo("data/noticias.json no es un arreglo")
    return datos


def guardar_noticias(lista, ruta=None, esquema=None):
    """Valida ANTES de escribir. Si no pasa, el archivo no se toca."""
    esquema = esquema or leer_json(RUTA_ESQUEMA)
    validar(lista, esquema)
    ruta = ruta or RUTA_NOTICIAS
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, ruta)
    return lista


def anotar_log(texto, ruta=None):
    ruta = ruta or RUTA_LOG
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    sello = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("%s | %s\n" % (sello, texto.replace("\n", " ")))


# ── Fechas y hora de Chile ──────────────────────────────────────────────────
def ahora_chile():
    """Hora de Chile continental sin depender de zoneinfo del sistema.

    Horario de verano: desde el primer sabado de septiembre hasta el primer
    sabado de abril, UTC-3; el resto del ano, UTC-4. La regla vigente la fija
    el Decreto 224/2022; si cambia, se ajusta aqui y en el workflow.
    """
    u = datetime.now(timezone.utc)
    return u + timedelta(hours=-3 if _en_horario_verano(u) else -4)


def _primer_sabado(ano, mes):
    d = datetime(ano, mes, 1, tzinfo=timezone.utc)
    return d + timedelta(days=(5 - d.weekday()) % 7)


def _en_horario_verano(u):
    inicio = _primer_sabado(u.year, 9)      # entra en septiembre
    fin = _primer_sabado(u.year, 4)         # sale en abril
    return u >= inicio or u < fin


def hoy_chile():
    return ahora_chile().strftime("%Y-%m-%d")


def a_fecha(texto):
    """Acepta ISO, RFC 822 (lo normal en RSS) y unos pocos formatos sueltos."""
    if not texto:
        return None
    texto = texto.strip()
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(texto)
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for patron in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(texto[:len("2026-11-22T00:00:00+0000")], patron)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def dentro_de_ventana(fecha_pub, dias):
    d = a_fecha(fecha_pub) if isinstance(fecha_pub, str) else fecha_pub
    if d is None:
        return False
    ahora = datetime.now(timezone.utc)
    return timedelta(0) <= (ahora - d) <= timedelta(days=dias, hours=12)


# ── Dominios ────────────────────────────────────────────────────────────────
def dominio_de(url):
    m = re.match(r"^https?://([^/?#]+)", (url or "").strip(), re.I)
    if not m:
        return ""
    host = m.group(1).lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def dominio_permitido(url, fuentes):
    host = dominio_de(url)
    if not host:
        return False
    for permitido in fuentes["dominios_permitidos"]:
        p = permitido.lower()
        if host == p or host.endswith("." + p):
            return True
    return False


# ── Texto ───────────────────────────────────────────────────────────────────
_ETIQUETAS = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


def limpiar(texto, maximo=None):
    """Quita etiquetas, resuelve entidades y deja una sola linea."""
    t = _ETIQUETAS.sub(" ", texto or "")
    t = _html.unescape(t)
    t = t.replace(" ", " ")
    t = _ESPACIOS.sub(" ", t).strip()
    if maximo and len(t) > maximo:
        corte = t[: maximo - 1].rsplit(" ", 1)[0]
        t = (corte if len(corte) > maximo * 0.6 else t[: maximo - 1]) + "…"
    return t


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", (texto or "").lower())
                   if unicodedata.category(c) != "Mn")


def nuevo_id(url, fecha=None):
    """Identificador estable: depende de la url, no del momento de guardar."""
    sello = (fecha or hoy_chile())[:10]
    h = hashlib.sha256((url or "").encode("utf-8")).hexdigest()
    return "%s-%s-%s" % (h[:4], sello, h[4:10])


# ── Duplicados ──────────────────────────────────────────────────────────────
def _normalizar_url(url):
    u = (url or "").strip().lower().split("#")[0]
    u = re.sub(r"[?&](utm_[^=]+|fbclid|gclid)=[^&]*", "", u)
    return u.rstrip("/?&")


def _firma_titulo(titulo):
    """Las diez palabras largas del titulo, ordenadas: detecta el mismo hecho
    contado por dos medios distintos."""
    palabras = [p for p in re.findall(r"[a-z0-9]+", sin_tildes(titulo)) if len(p) > 4]
    return " ".join(sorted(set(palabras))[:10])


def es_duplicada(candidata, lista):
    u = _normalizar_url(candidata.get("url"))
    f = _firma_titulo(candidata.get("titulo"))
    for n in lista:
        if _normalizar_url(n.get("url")) == u:
            return "misma url"
        if f and _firma_titulo(n.get("titulo")) == f:
            return "mismo hecho, otro enlace"
    return None


# ── Rotacion ────────────────────────────────────────────────────────────────
def rotar(lista, nueva, maximo=3):
    """Mete la nueva adelante y deja fuera la mas antigua. Devuelve
    (lista_nueva, descartada_o_None)."""
    quedan = [nueva] + list(lista)
    descartada = quedan[maximo] if len(quedan) > maximo else None
    return quedan[:maximo], descartada


# ── Validacion contra el esquema ────────────────────────────────────────────
def _validar_campo(nombre, valor, regla, donde):
    tipo = regla["tipo"]
    req = regla.get("requerido", False)

    if valor is None or valor == "":
        if req and not (tipo == "texto" and regla.get("min", 1) == 0):
            raise Rechazo("%s: falta %s" % (donde, nombre))
        if tipo == "texto" and regla.get("min", 1) == 0:
            return
        if not req:
            return

    if tipo == "objeto":
        if not isinstance(valor, dict):
            raise Rechazo("%s: %s deberia ser un objeto" % (donde, nombre))
        for sub, subregla in regla["campos"].items():
            _validar_campo(sub, valor.get(sub), subregla, "%s.%s" % (donde, nombre))
        return

    if tipo == "entero":
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise Rechazo("%s: %s deberia ser un numero entero" % (donde, nombre))
        if "min" in regla and valor < regla["min"]:
            raise Rechazo("%s: %s fuera de rango" % (donde, nombre))
        if "max" in regla and valor > regla["max"]:
            raise Rechazo("%s: %s fuera de rango" % (donde, nombre))
        return

    if not isinstance(valor, str):
        raise Rechazo("%s: %s deberia ser texto" % (donde, nombre))

    if tipo == "fecha":
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", valor):
            raise Rechazo("%s: %s no tiene formato AAAA-MM-DD" % (donde, nombre))
        return

    if tipo == "url":
        if not valor.startswith("https://"):
            raise Rechazo("%s: la url debe ser https" % donde)
        if len(valor) > regla.get("max", 500):
            raise Rechazo("%s: url demasiado larga" % donde)
        return

    if "min" in regla and len(valor) < regla["min"]:
        raise Rechazo("%s: %s demasiado corto (%d)" % (donde, nombre, len(valor)))
    if "max" in regla and len(valor) > regla["max"]:
        raise Rechazo("%s: %s demasiado largo (%d)" % (donde, nombre, len(valor)))
    if "patron" in regla and not re.match(regla["patron"], valor):
        raise Rechazo("%s: %s no cuadra con el patron" % (donde, nombre))
    if "valores" in regla and valor not in regla["valores"]:
        raise Rechazo("%s: %s='%s' no es un valor admitido" % (donde, nombre, valor))


def validar(lista, esquema=None, fuentes=None):
    esquema = esquema or leer_json(RUTA_ESQUEMA)
    if not isinstance(lista, list):
        raise Rechazo("la raiz deberia ser un arreglo")
    if len(lista) > esquema["maximo"]:
        raise Rechazo("hay %d noticias y el maximo es %d" % (len(lista), esquema["maximo"]))

    vistas_url, vistos_id = set(), set()
    for i, n in enumerate(lista):
        donde = "noticia %d" % (i + 1)
        if not isinstance(n, dict):
            raise Rechazo("%s: no es un objeto" % donde)
        for nombre, regla in esquema["campos"].items():
            _validar_campo(nombre, n.get(nombre), regla, donde)
        if n.get("origen") == "rss" and (n.get("por_que_importa") or "").strip():
            raise Rechazo("%s: con origen rss, por_que_importa va vacio" % donde)
        u = _normalizar_url(n["url"])
        if u in vistas_url:
            raise Rechazo("%s: url repetida" % donde)
        vistas_url.add(u)
        if n["id"] in vistos_id:
            raise Rechazo("%s: id repetido" % donde)
        vistos_id.add(n["id"])
        if fuentes and not dominio_permitido(n["url"], fuentes):
            raise Rechazo("%s: %s no esta en la lista blanca" % (donde, dominio_de(n["url"])))
    return True
