# -*- coding: utf-8 -*-
"""Pruebas de la seccion Actualidad. Sin dependencias: python scripts/probar_noticias.py

Cubren lo que puede romperse en silencio: que la cuarta noticia expulse a la
mas antigua, que no entre dos veces el mismo hecho, que un dominio ajeno no
pase, que un dia sin candidatas buenas no publique nada, y que el JSON no se
guarde si no cuadra con el esquema.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noticias_lib as L  # noqa: E402
import noticias_rss as R  # noqa: E402

VERDE, ROJO, FIN = "\033[32m", "\033[31m", "\033[0m"
fallos = []


def prueba(nombre):
    def envoltorio(fn):
        try:
            fn()
            print("  %sOK  %s %s" % (VERDE, FIN, nombre))
        except AssertionError as e:
            fallos.append(nombre)
            print("  %sMAL %s %s  ->  %s" % (ROJO, FIN, nombre, e))
        except Exception as e:
            fallos.append(nombre)
            print("  %sMAL %s %s  ->  %s: %s" % (ROJO, FIN, nombre, type(e).__name__, e))
        return fn
    return envoltorio


def noticia(n, url=None, titulo=None, origen="claude-code", ingreso="2026-11-20"):
    u = url or ("https://www.mineduc.cl/nota-%d/" % n)
    return {
        "id": L.nuevo_id(u, ingreso),
        "titulo": titulo or ("Titular de prueba numero %d sobre convivencia escolar" % n),
        "resumen": "Resumen de prueba con el largo suficiente para pasar el esquema sin problemas.",
        "por_que_importa": "" if origen == "rss" else "Le importa a su colegio por esta razon concreta.",
        "servicio": {"numero": 4, "nombre": "Convivencia Educativa"},
        "fuente": "Ministerio de Educación",
        "url": u,
        "fecha_publicacion": "2026-11-19",
        "fecha_ingreso": ingreso,
        "origen": origen,
    }


FUENTES = L.leer_json(L.RUTA_FUENTES)
ESQUEMA = L.leer_json(L.RUTA_ESQUEMA)
PALABRAS = L.leer_json(L.RUTA_PALABRAS)

print("\n  Pruebas de la seccion Actualidad\n")
print("  1 · Rotacion FIFO")


@prueba("tres noticias caben sin expulsar a nadie")
def _():
    lista = []
    for i in (1, 2, 3):
        lista, fuera = L.rotar(lista, noticia(i))
        assert fuera is None, "expulso a alguien antes de llenarse"
    assert len(lista) == 3, "deberian quedar 3 y quedaron %d" % len(lista)


@prueba("la cuarta expulsa a la mas antigua, no a otra")
def _():
    lista = []
    for i in (1, 2, 3):
        lista, _ = L.rotar(lista, noticia(i))
    primera = lista[-1]["id"]
    lista, fuera = L.rotar(lista, noticia(4))
    assert len(lista) == 3, "quedaron %d noticias" % len(lista)
    assert fuera is not None and fuera["id"] == primera, "expulso la que no era"
    assert all(n["id"] != primera for n in lista), "la expulsada sigue en la lista"


@prueba("la mas reciente queda primera")
def _():
    lista = []
    for i in (1, 2, 3, 4):
        lista, _ = L.rotar(lista, noticia(i))
    assert "nota-4" in lista[0]["url"], "la cabecera no es la ultima que entro"


print("\n  2 · Duplicados")


@prueba("misma url, aunque cambie el titulo")
def _():
    base = [noticia(1)]
    otra = noticia(1, titulo="Un titular completamente distinto del anterior")
    assert L.es_duplicada(otra, base) == "misma url"


@prueba("misma url con utm y barra final")
def _():
    base = [noticia(1)]
    otra = noticia(9, url="https://www.mineduc.cl/nota-1?utm_source=boletin")
    assert L.es_duplicada(otra, base), "no detecto la url con parametros de campana"


@prueba("mismo hecho contado por otro medio")
def _():
    base = [noticia(1, titulo="Superintendencia multa a colegio por no aplicar protocolo de convivencia")]
    otra = noticia(2, url="https://www.latercera.com/nota/",
                   titulo="Protocolo de convivencia: Superintendencia multa colegio por no aplicar")
    assert L.es_duplicada(otra, base) == "mismo hecho, otro enlace"


@prueba("dos noticias distintas no se confunden")
def _():
    base = [noticia(1, titulo="Mineduc publica orientaciones sobre celulares en el aula")]
    otra = noticia(2, url="https://www.supereduc.cl/otra/",
                   titulo="Denuncias por ciberacoso aumentan en establecimientos de la region")
    assert L.es_duplicada(otra, base) is None, "marco como duplicada una noticia distinta"


print("\n  3 · Lista blanca de dominios")


@prueba("un dominio de la lista pasa")
def _():
    assert L.dominio_permitido("https://www.mineduc.cl/algo/", FUENTES)


@prueba("un subdominio de la lista pasa")
def _():
    assert L.dominio_permitido("https://noticias.latercera.com/nota/", FUENTES)


@prueba("un dominio ajeno no pasa")
def _():
    for u in ("https://noticias-falsas.cl/nota/",
              "https://www.mineduc.cl.atacante.com/nota/",
              "https://medium.com/@alguien/mineduc"):
        assert not L.dominio_permitido(u, FUENTES), "dejo pasar %s" % u


@prueba("guardar rechaza una noticia de dominio ajeno")
def _():
    mala = noticia(1, url="https://noticias-falsas.cl/nota/")
    try:
        L.validar([mala], ESQUEMA, FUENTES)
        assert False, "la acepto"
    except L.Rechazo as e:
        assert "lista blanca" in str(e), "rechazo por otro motivo: %s" % e


print("\n  4 · Sin publicacion")


@prueba("un dia sin candidatas sobre el umbral no publica")
def _():
    entrada = {"titulo": "La seleccion chilena define su formacion para el amistoso",
               "extracto": "El entrenador adelanto el once titular del partido.",
               "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": "https://www.latercera.com/deportes/nota/",
               "fuente": FUENTES["feeds"][4]}
    puntaje, _, _ = R.puntuar(entrada, PALABRAS)
    assert puntaje < FUENTES["umbral_relevancia"], "le dio %d a una noticia de futbol" % puntaje


@prueba("una noticia del tema si supera el umbral")
def _():
    entrada = {"titulo": "Mineduc publica el reglamento de la Ley 21.801 sobre celulares en el aula",
               "extracto": "Los establecimientos deberan adecuar su reglamento interno de convivencia escolar.",
               "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": "https://www.mineduc.cl/nota/",
               "fuente": FUENTES["feeds"][0]}
    puntaje, servicio, _ = R.puntuar(entrada, PALABRAS)
    assert puntaje >= FUENTES["umbral_relevancia"], "solo le dio %d" % puntaje
    assert servicio[0] == "4", "la mando al servicio %s" % servicio[0]


@prueba("un medio con un tema del programa tambien pasa")
def _():
    entrada = {"titulo": "Aumentan las denuncias por ciberacoso en colegios de la region",
               "extracto": "Los establecimientos reportan mas casos entre estudiantes.",
               "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": "https://www.latercera.com/nota/",
               "fuente": FUENTES["feeds"][4]}
    puntaje, servicio, _ = R.puntuar(entrada, PALABRAS)
    assert puntaje >= FUENTES["umbral_relevancia"], "solo le dio %d a un tema del programa" % puntaje
    assert servicio[0] == "7", "lo mando al servicio %s" % servicio[0]


@prueba("una nota generica sin contexto escolar se castiga")
def _():
    entrada = {"titulo": "Empresa de retail sufre filtracion de datos personales de clientes",
               "extracto": "La compania informo el incidente a la autoridad.",
               "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "url": "https://www.latercera.com/nota/",
               "fuente": FUENTES["feeds"][4]}
    puntaje, _, _ = R.puntuar(entrada, PALABRAS)
    assert puntaje < FUENTES["umbral_relevancia"], "le dio %d sin hablar de colegios" % puntaje


@prueba("una noticia vieja no pasa la ventana")
def _():
    vieja = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not L.dentro_de_ventana(vieja, 7)
    reciente = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert L.dentro_de_ventana(reciente, 7)


print("\n  5 · Esquema y guardado")


@prueba("el archivo que hay hoy en el repositorio es valido")
def _():
    L.validar(L.cargar_noticias(), ESQUEMA, FUENTES)


@prueba("no se admiten mas de tres")
def _():
    try:
        L.validar([noticia(i) for i in range(1, 5)], ESQUEMA, FUENTES)
        assert False, "acepto cuatro"
    except L.Rechazo:
        pass


@prueba("con origen rss, por_que_importa va vacio")
def _():
    n = noticia(1, origen="rss")
    n["por_que_importa"] = "algo"
    try:
        L.validar([n], ESQUEMA, FUENTES)
        assert False, "lo acepto"
    except L.Rechazo:
        pass


@prueba("una url http sin cifrar se rechaza")
def _():
    n = noticia(1)
    n["url"] = "http://www.mineduc.cl/nota/"
    try:
        L.validar([n], ESQUEMA, FUENTES)
        assert False, "acepto http"
    except L.Rechazo:
        pass


@prueba("si el JSON no cuadra, el archivo no se toca")
def _():
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "noticias.json")
        L.guardar_noticias([noticia(1)], ruta, ESQUEMA)
        antes = open(ruta, encoding="utf-8").read()
        malo = noticia(2)
        del malo["titulo"]
        try:
            L.guardar_noticias([malo], ruta, ESQUEMA)
            assert False, "guardo un JSON invalido"
        except L.Rechazo:
            pass
        assert open(ruta, encoding="utf-8").read() == antes, "el archivo quedo alterado"
        assert json.loads(antes)[0]["titulo"], "lo guardado no se relee"


print("\n  6 · Texto y seguridad")


@prueba("el extracto pierde las etiquetas HTML")
def _():
    sucio = '<p>Hola <b>mundo</b><script>alert(1)</script> &amp; adios</p>'
    limpio = L.limpiar(sucio)
    assert "<" not in limpio and "script" not in limpio.lower(), limpio
    assert "&" in limpio, "no resolvio la entidad"


@prueba("el resumen se recorta a 200 caracteres")
def _():
    largo = "palabra " * 200
    assert len(L.limpiar(largo, 200)) <= 200


@prueba("el id depende de la url, no del reloj")
def _():
    a = L.nuevo_id("https://www.mineduc.cl/x/", "2026-11-22")
    b = L.nuevo_id("https://www.mineduc.cl/x/", "2026-11-22")
    c = L.nuevo_id("https://www.mineduc.cl/y/", "2026-11-22")
    assert a == b and a != c


@prueba("la hora de Chile cambia con el horario de verano")
def _():
    assert L._en_horario_verano(datetime(2026, 1, 15, tzinfo=timezone.utc)), "enero es verano"
    assert not L._en_horario_verano(datetime(2026, 6, 15, tzinfo=timezone.utc)), "junio es invierno"
    assert L._en_horario_verano(datetime(2026, 12, 15, tzinfo=timezone.utc)), "diciembre es verano"


print("")
if fallos:
    print("%s  %d prueba(s) fallaron: %s%s\n" % (ROJO, len(fallos), ", ".join(fallos), FIN))
    sys.exit(1)
print("%s  Todas las pruebas pasaron%s\n" % (VERDE, FIN))
