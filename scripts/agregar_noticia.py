# -*- coding: utf-8 -*-
"""Agrega una noticia verificada a data/noticias.json, con todas las guardas.

Lo usa /noticia-del-dia en el paso de guardar. Hace la rotacion FIFO, valida
contra el esquema, comprueba la lista blanca y escribe solo si todo cuadra: si
algo falla, el archivo queda como estaba y el motivo sale por pantalla.

    python scripts/agregar_noticia.py --archivo nueva.json
    python scripts/agregar_noticia.py --json '{"titulo": "...", ...}'

Campos que hay que entregar (el id y las fechas se completan solos si faltan):
    titulo, resumen, por_que_importa, servicio {numero, nombre},
    fuente, url, fecha_publicacion
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noticias_lib as L  # noqa: E402

NOMBRES = {
    1: "Ley Marco de Ciberseguridad",
    2: "Capacitación en ciberseguridad educativa",
    3: "Calendario Escolar",
    4: "Convivencia Educativa",
    5: "Protección de Datos Personales",
    6: "Inclusión y PIE",
    7: "Escuela para Padres",
}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="la noticia como texto JSON")
    g.add_argument("--archivo", help="archivo con la noticia en JSON")
    ap.add_argument("--seco", action="store_true", help="valida y muestra, sin escribir")
    args = ap.parse_args()

    crudo = args.json if args.json else open(args.archivo, encoding="utf-8").read()
    try:
        nueva = json.loads(crudo)
    except json.JSONDecodeError as e:
        print("El JSON no se puede leer: %s" % e)
        return 1

    fuentes, _, esquema = L.cargar_config()
    hoy = L.hoy_chile()

    nueva.setdefault("origen", "claude-code")
    nueva.setdefault("fecha_ingreso", hoy)
    nueva.setdefault("fecha_publicacion", hoy)
    nueva.setdefault("por_que_importa", "")
    if isinstance(nueva.get("servicio"), int):
        nueva["servicio"] = {"numero": nueva["servicio"],
                             "nombre": NOMBRES.get(nueva["servicio"], "")}
    if isinstance(nueva.get("servicio"), dict) and not nueva["servicio"].get("nombre"):
        nueva["servicio"]["nombre"] = NOMBRES.get(nueva["servicio"].get("numero"), "")
    nueva.setdefault("id", L.nuevo_id(nueva.get("url", ""), nueva["fecha_ingreso"]))

    for campo in ("titulo", "resumen", "url", "fuente"):
        if isinstance(nueva.get(campo), str):
            nueva[campo] = L.limpiar(nueva[campo])

    publicadas = L.cargar_noticias()

    if not L.dominio_permitido(nueva.get("url", ""), fuentes):
        print("RECHAZADA: %s no esta en la lista blanca de config/fuentes.json"
              % (L.dominio_de(nueva.get("url", "")) or "la url"))
        return 1
    repetida = L.es_duplicada(nueva, publicadas)
    if repetida:
        print("RECHAZADA: ya esta publicada (%s)" % repetida)
        return 1
    if not L.dentro_de_ventana(nueva["fecha_publicacion"], fuentes["ventana_dias"]):
        print("RECHAZADA: la fecha %s queda fuera de los %d dias de la ventana"
              % (nueva["fecha_publicacion"], fuentes["ventana_dias"]))
        return 1

    lista, fuera = L.rotar(publicadas, nueva, esquema["maximo"])
    try:
        L.validar(lista, esquema, fuentes)
    except L.Rechazo as e:
        print("RECHAZADA: %s" % e)
        return 1

    print("Lista para guardar:")
    print("  %s" % nueva["titulo"])
    print("  %s · servicio %s · %s" % (nueva["fuente"], nueva["servicio"]["numero"],
                                       nueva["fecha_publicacion"]))
    print("  sale de rotacion: %s" % (fuera["titulo"][:70] if fuera else "ninguna, aun hay sitio"))

    if args.seco:
        print("(--seco: no se escribio nada)")
        return 0

    L.guardar_noticias(lista, esquema=esquema)
    L.anotar_log("comando | publicada | %s | %s | servicio %s | sale: %s" % (
        nueva["fuente"], nueva["url"], nueva["servicio"]["numero"],
        fuera["id"] if fuera else "ninguna"))
    print("Guardada. Quedan %d noticias en data/noticias.json" % len(lista))
    return 0


if __name__ == "__main__":
    sys.exit(main())
