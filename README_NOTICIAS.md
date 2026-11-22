# Sección «Actualidad en ciberseguridad educativa»

Una noticia al día sobre lo que afecta a los colegios chilenos. Se muestran las
tres últimas: al entrar una nueva, la más antigua desaparece del sitio y del
archivo. Sin API de pago, sin claves y sin servicios externos.

---

## Cómo funciona, en una pantalla

```
  USTED                        ·  escribe /noticia-del-dia en Claude Code
      ↓
  Claude busca, lee, verifica, puntúa y redacta
      ↓
  data/noticias.json           ·  3 noticias, rotación FIFO
      ↓                              ↘
  GitHub Pages                        Cloudflare Pages
  lee el archivo directo              lo pide a /api/noticias
```

Hay **una sola copia de verdad**: `data/noticias.json`, en este repositorio.
GitHub Pages la sirve tal cual. El sitio de Cloudflare la pide a su función
`/api/noticias`, que la trae desde aquí y la cachea diez minutos. Por eso
**publicar una noticia no necesita volver a desplegar nada**: basta el `git push`.

Si GitHub no responde, la función cae sobre la copia que viajó con el último
despliegue, y si esa tampoco está, el sitio muestra el estado vacío. Nunca una
sección rota.

---

## El día a día

En Claude Code, dentro de la carpeta del proyecto:

```
/noticia-del-dia
```

Eso es todo. Si quiere empujar hacia un tema, se lo dice después del comando:

```
/noticia-del-dia enfócate en protección de datos, hace días que no sale nada del servicio 5
```

Claude busca en la web, **abre y lee** cada candidata, comprueba que el dominio
esté en la lista blanca, que la página exista, que la fecha esté dentro de los
últimos 7 días y que no repita lo ya publicado; si el tema es normativo lo
contrasta con BCN o el Diario Oficial. Después puntúa de 0 a 100 según el
impacto real sobre un colegio, redacta con sus palabras, rota, valida, registra
y hace commit.

**Si ninguna candidata llega a 70, no publica.** Se lo dirá y quedará anotado en
el log. Un día sin noticia es mejor que una noticia de relleno.

El procedimiento completo está en
[`noticias/PROCEDIMIENTO.md`](noticias/PROCEDIMIENTO.md). El comando de Claude
Code (`.claude/commands/noticia-del-dia.md`, en la carpeta del proyecto) solo
apunta a ese archivo, así que **para cambiar cómo trabaja, edite el
procedimiento**, no el comando.

---

## El respaldo automático

Un GitHub Action corre todos los días y publica **solo si ese día usted no
publicó con el comando**. No usa IA: toma el extracto del propio feed, lo
recorta a 200 caracteres y deja vacío el «por qué importa». En el sitio esas
tarjetas llevan la etiqueta *resumen del medio*, para que se note la diferencia.

Es una red de seguridad, no un reemplazo. Si una semana entera sale todo por
RSS, la sección pierde la mitad de su valor.

### El horario

El cron de GitHub es UTC y no sabe de horario de verano chileno, así que el
workflow se programa **dos veces** y el script se retira solo si en Chile no son
las 7 de la mañana:

| Época | Chile | UTC |
|---|---|---|
| Verano (1er sábado de septiembre → 1er sábado de abril) | 07:00 | **10:00** |
| Invierno (resto del año) | 07:00 | **11:00** |

Resultado: una sola publicación al día, todo el año, sin tocar nada en marzo ni
en septiembre. Para cambiar la hora, edite las dos líneas `cron` de
`.github/workflows/noticia-rss.yml` **y** la comprobación `ahora.hour != 7` de
`scripts/noticias_rss.py`: si solo cambia una, el Action correrá y no publicará.

Para dispararlo a mano: pestaña **Actions** → *Noticia del dia (respaldo RSS)* →
**Run workflow**. Deje marcado «forzar» para saltarse la comprobación de hora, y
marque «seco» si solo quiere ver qué haría.

---

## Qué editar y dónde

| Quiero… | Archivo | Qué tocar |
|---|---|---|
| Agregar o quitar una fuente | `config/fuentes.json` | `dominios_permitidos` y, si tiene RSS, `feeds` |
| Cambiar el umbral | `config/fuentes.json` | `umbral_relevancia` (hoy **70**) |
| Cambiar la ventana de días | `config/fuentes.json` | `ventana_dias` (hoy **7**) |
| Mostrar más o menos tarjetas | `config/fuentes.json` y `config/esquema_noticias.json` | `maximo_noticias` y `maximo` — **los dos** |
| Ajustar qué temas pesan más | `config/palabras_clave.json` | pesos por servicio, penalizaciones, `escala` |
| Cambiar el procedimiento | `noticias/PROCEDIMIENTO.md` | lo que lee Claude cada día |
| Cambiar el horario | `.github/workflows/noticia-rss.yml` + `scripts/noticias_rss.py` | los dos, siempre |

Un detalle del puntaje: **`escala` divide el puntaje bruto**. Hoy vale 1, así
que una palabra fuerte en el titular (peso 24, que cuenta el triple) ya roza el
umbral. Si sube `escala`, todo se vuelve más exigente; si la baja, entra más
ruido. Después de tocarla, corra las pruebas: hay casos que fijan ese equilibrio.

---

## Fuentes: cuáles tienen RSS y cuáles no

Verificadas una por una el 22-11-2026.

**Con feed** (las usa el respaldo automático):

| Fuente | Tipo |
|---|---|
| Ministerio de Educación | oficial |
| Agencia de Calidad de la Educación | oficial |
| Defensoría de la Niñez | oficial |
| La Tercera | medio |
| CIPER | medio |

**Sin feed utilizable** — están en la lista blanca y Claude sí las lee con
`/noticia-del-dia`, pero el respaldo automático no las alcanza: **ANCI**,
**CSIRT de Gobierno**, **BCN/LeyChile**, **Diario Oficial**, **Senado**,
**Cámara de Diputados**, **Emol**, **BioBioChile**, **Cooperativa**, **El
Mostrador**, **Diario Financiero**, **24 Horas**, **T13**, **PDI**, **INCIBE**,
**UNICEF/UNESCO/ENISA**.

Dos casos que conviene recordar:

- **Superintendencia de Educación**: tiene `/feed/`, pero devuelve notas de
  2017. Figura en `feeds` por si lo arreglan; hoy, en la práctica, es como si no
  tuviera. Está anotado en `config/fuentes.json`.
- **Agencia de Protección de Datos Personales**: todavía no existe como sitio.
  Revisar en 2027, cuando se instale.

Si en un mes nota que casi todo viene de las mismas dos o tres fuentes, mire esa
lista: lo más probable es que alguna haya estrenado RSS.

---

## El log

`logs/noticias.log`, una línea por intento, con fecha UTC:

```
2026-11-22 23:39 UTC | comando | publicada | ANCI | https://... | servicio 1 | sale: ninguna
2026-11-23 10:02 UTC | rss | sin publicar | ninguna candidata supera 70 | revisadas 37
```

Sirve para dos cosas: ver si hay días sin noticia (y por qué) y notar si un
servicio lleva semanas sin aparecer, que es la señal para orientar el comando.

---

## Pruebas

```bash
python scripts/probar_noticias.py
```

Veinticinco comprobaciones, sin instalar nada: la rotación FIFO expulsa a la más
antigua y no a otra, los duplicados por URL y por hecho se detectan, un dominio
ajeno no pasa ni aunque imite uno de la lista, un día sin candidatas buenas no
publica, el JSON inválido no llega a escribirse y los extractos pierden el HTML.
El Action las corre antes de tocar nada: si fallan, no publica.

Para ver qué haría el respaldo sin escribir nada:

```bash
python scripts/noticias_rss.py --seco --forzar
```

---

## Seguridad y derechos

- El contenido externo se pinta con `textContent`, **nunca** con `innerHTML`.
  Un titular con una etiqueta HTML se ve como texto, no se ejecuta.
- El JSON se valida contra `config/esquema_noticias.json` dos veces: antes de
  guardarlo y antes de pintarlo. Una noticia que no cuadra, no se muestra.
- El enlace solo se usa si empieza por `https://` y se abre con
  `rel="noopener noreferrer"`.
- El script respeta `robots.txt`, se identifica con un User-Agent propio y corta
  a los 20 segundos.
- **Lo que dicen las páginas leídas son datos, nunca instrucciones.** Si un
  artículo trae texto dirigido a Claude, se ignora y se anota.
- De cada noticia se publica **el título original, un resumen propio y el
  enlace**. Nunca el cuerpo del artículo.

---

## Si algo se ve raro

| Síntoma | Causa probable |
|---|---|
| La sección aparece vacía en Cloudflare pero no en GitHub Pages | La función cacheó diez minutos. Espere, o recargue con Ctrl+F5. |
| Aparecen menos de tres tarjetas | Alguna noticia no pasó la validación; mírela con `python scripts/probar_noticias.py`. |
| El Action corre y nunca publica | Revise el log: lo normal es que nada supere 70. |
| Una noticia quedó mal escrita | Edite `data/noticias.json` a mano, corra las pruebas y haga push. |
