# -*- coding: utf-8 -*-
"""Respaldo automatico de la seccion Actualidad, sin IA.

Lee los feeds de config/fuentes.json, puntua cada entrada con las palabras de
config/palabras_clave.json y publica la mejor, si supera el umbral. No redacta:
el resumen es el extracto del propio feed, limpio de etiquetas y recortado.
Por eso deja el campo por_que_importa vacio y marca origen "rss": para que se
note, en el sitio y en el log, que ese dia no paso por /noticia-del-dia.

Solo publica si ese dia no se publico ya. Biblioteca estandar, sin instalar nada.

    python scripts/noticias_rss.py            publica si corresponde
    python scripts/noticias_rss.py --seco     dice que haria, sin escribir
    python scripts/noticias_rss.py --forzar   ignora la hora de Chile
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

sys.path.insert(0, __file__.rsplit("noticias_rss.py", 1)[0])
import noticias_lib as L  # noqa: E402

TIEMPO_LIMITE = 20
ESPACIOS_ATOM = {"a": "http://www.w3.org/2005/Atom"}
_robots_cache = {}


# ── Red ─────────────────────────────────────────────────────────────────────
def traer(url, limite_bytes=2_000_000):
    pedido = urllib.request.Request(url, headers={
        "User-Agent": L.AGENTE,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html",
        "Accept-Language": "es-CL,es;q=0.9",
    })
    with urllib.request.urlopen(pedido, timeout=TIEMPO_LIMITE) as r:
        return r.status, r.geturl(), r.read(limite_bytes)


def robots_permite(url):
    """Respeta robots.txt. Si el archivo no se puede leer, se asume que si."""
    partes = urlparse(url)
    base = "%s://%s" % (partes.scheme, partes.netloc)
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    if rp is None:
        return True
    try:
        return rp.can_fetch(L.AGENTE, url)
    except Exception:
        return True


# ── Feeds ───────────────────────────────────────────────────────────────────
def _texto(nodo, *caminos):
    for c in caminos:
        hijo = nodo.find(c) if ":" not in c else nodo.find(c, ESPACIOS_ATOM)
        if hijo is not None:
            if hijo.text and hijo.text.strip():
                return hijo.text.strip()
            if hijo.get("href"):
                return hijo.get("href").strip()
    return ""


def leer_feed(fuente):
    """Devuelve las entradas de un feed RSS 2.0 o Atom."""
    try:
        estado, _, crudo = traer(fuente["url"])
    except Exception as e:
        return [], "no respondio (%s)" % type(e).__name__
    if estado != 200:
        return [], "HTTP %s" % estado
    try:
        raiz = ET.fromstring(crudo)
    except ET.ParseError as e:
        return [], "XML ilegible (%s)" % e

    entradas = []
    for item in raiz.iter():
        etiqueta = item.tag.split("}")[-1]
        if etiqueta not in ("item", "entry"):
            continue
        titulo = L.limpiar(_texto(item, "title", "a:title"))
        enlace = _texto(item, "link", "a:link")
        if not enlace:
            hijo = item.find("a:link", ESPACIOS_ATOM)
            enlace = hijo.get("href") if hijo is not None else ""
        fecha = _texto(item, "pubDate", "a:published", "a:updated",
                       "{http://purl.org/dc/elements/1.1/}date")
        extracto = L.limpiar(_texto(item, "description", "a:summary", "a:content",
                                    "{http://purl.org/rss/1.0/modules/content/}encoded"))
        if titulo and enlace:
            entradas.append({"titulo": titulo, "url": enlace.strip(),
                             "fecha": fecha, "extracto": extracto, "fuente": fuente})
    return entradas, None


# ── Puntaje ─────────────────────────────────────────────────────────────────
def puntuar(entrada, palabras):
    titulo = L.sin_tildes(entrada["titulo"])
    cuerpo = L.sin_tildes(entrada["extracto"])
    completo = titulo + " " + cuerpo

    mejor_servicio, mejor_bruto = None, 0.0
    for numero, servicio in palabras["servicios"].items():
        bruto = 0.0
        for palabra, peso in servicio["palabras"].items():
            p = L.sin_tildes(palabra)
            if p in titulo:
                bruto += peso * palabras["factor_titulo"]
            elif p in cuerpo:
                bruto += peso * palabras["factor_extracto"]
        if bruto > mejor_bruto:
            mejor_servicio, mejor_bruto = (numero, servicio["nombre"]), bruto

    if mejor_servicio is None:
        return 0, None, "ninguna palabra clave"

    if entrada["fuente"]["tipo"] == "oficial":
        mejor_bruto += palabras["bonificacion_fuente_oficial"] * palabras["factor_titulo"]

    for palabra, castigo in palabras["penalizacion"].items():
        if palabra.startswith("_"):
            continue
        if L.sin_tildes(palabra) in completo:
            mejor_bruto -= castigo * palabras["factor_titulo"]

    ctx = palabras["exige_contexto_escolar"]
    if not any(L.sin_tildes(p) in completo for p in ctx["palabras"]):
        mejor_bruto -= ctx["castigo"] * palabras["factor_titulo"]

    bruto = mejor_bruto * entrada["fuente"]["peso"]
    puntaje = max(0, min(100, int(round(bruto / palabras["escala"]))))
    return puntaje, mejor_servicio, None


# ── Verificacion ────────────────────────────────────────────────────────────
def verificar(entrada, fuentes, publicadas):
    url = entrada["url"]
    if not L.dominio_permitido(url, fuentes):
        return "dominio fuera de la lista blanca (%s)" % L.dominio_de(url)
    if not L.dentro_de_ventana(entrada["fecha"], fuentes["ventana_dias"]):
        return "sin fecha legible o fuera de los %d dias" % fuentes["ventana_dias"]
    repetida = L.es_duplicada(entrada, publicadas)
    if repetida:
        return "duplicada: %s" % repetida
    if not robots_permite(url):
        return "robots.txt no permite leerla"
    try:
        estado, final, _ = traer(url, limite_bytes=200_000)
    except Exception as e:
        return "no se pudo abrir (%s)" % type(e).__name__
    if estado != 200:
        return "la pagina responde HTTP %s" % estado
    if not L.dominio_permitido(final, fuentes):
        return "redirige fuera de la lista blanca (%s)" % L.dominio_de(final)
    return None


# ── Principal ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true", help="no escribe nada")
    ap.add_argument("--forzar", action="store_true", help="ignora la comprobacion de hora")
    args = ap.parse_args()

    fuentes, palabras, esquema = L.cargar_config()
    publicadas = L.cargar_noticias()

    ahora = L.ahora_chile()
    if not args.forzar and ahora.hour != 7:
        print("No son las 07:00 en Chile (son las %02d:%02d). El Action corre dos veces "
              "por el horario de verano; esta no es la buena." % (ahora.hour, ahora.minute))
        return 0

    hoy = L.hoy_chile()
    if publicadas and publicadas[0].get("fecha_ingreso") == hoy:
        motivo = "ya hay noticia de hoy (origen %s); el respaldo no interviene" % publicadas[0].get("origen")
        print(motivo)
        if not args.seco:
            L.anotar_log("rss | sin publicar | " + motivo)
        return 0

    candidatas, problemas = [], []
    for fuente in fuentes["feeds"]:
        entradas, error = leer_feed(fuente)
        if error:
            problemas.append("%s: %s" % (fuente["nombre"], error))
            continue
        for e in entradas:
            puntaje, servicio, _ = puntuar(e, palabras)
            if puntaje > 0:
                e["puntaje"], e["servicio"] = puntaje, servicio
                candidatas.append(e)

    candidatas.sort(key=lambda e: e["puntaje"], reverse=True)
    for p in problemas:
        print("  feed con problemas ·", p)

    elegida, descartes = None, []
    for e in candidatas[:12]:
        if e["puntaje"] < fuentes["umbral_relevancia"]:
            descartes.append("%s (%d, bajo el umbral)" % (e["titulo"][:60], e["puntaje"]))
            break
        motivo = verificar(e, fuentes, publicadas)
        if motivo:
            descartes.append("%s (%d, %s)" % (e["titulo"][:60], e["puntaje"], motivo))
            continue
        elegida = e
        break

    for d in descartes:
        print("  descartada ·", d)

    if not elegida:
        motivo = "ninguna candidata supera %d y verifica" % fuentes["umbral_relevancia"]
        print("Sin publicacion:", motivo)
        if not args.seco:
            L.anotar_log("rss | sin publicar | %s | revisadas %d" % (motivo, len(candidatas)))
        return 0

    fecha_pub = L.a_fecha(elegida["fecha"]) or datetime.now(timezone.utc)
    noticia = {
        "id": L.nuevo_id(elegida["url"], hoy),
        "titulo": L.limpiar(elegida["titulo"], 220),
        "resumen": L.limpiar(elegida["extracto"] or elegida["titulo"], 200),
        "por_que_importa": "",
        "servicio": {"numero": int(elegida["servicio"][0]), "nombre": elegida["servicio"][1]},
        "fuente": elegida["fuente"]["nombre"],
        "url": elegida["url"],
        "fecha_publicacion": fecha_pub.strftime("%Y-%m-%d"),
        "fecha_ingreso": hoy,
        "origen": "rss",
    }
    if len(noticia["resumen"]) < 20:
        noticia["resumen"] = L.limpiar(elegida["titulo"], 200)

    lista, fuera = L.rotar(publicadas, noticia, esquema["maximo"])
    L.validar(lista, esquema, fuentes)

    print("Publicaria:", noticia["titulo"])
    print("  fuente %s · servicio %s · puntaje %d" %
          (noticia["fuente"], noticia["servicio"]["numero"], elegida["puntaje"]))
    if fuera:
        print("  sale de rotacion:", fuera["titulo"][:70])

    if args.seco:
        print("(--seco: no se escribio nada)")
        return 0

    L.guardar_noticias(lista, esquema=esquema)
    L.anotar_log("rss | publicada | %s | %s | puntaje %d | sale: %s" % (
        noticia["fuente"], noticia["url"], elegida["puntaje"],
        fuera["id"] if fuera else "ninguna"))
    print("Guardada en data/noticias.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
