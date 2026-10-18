"""Gera um KMZ com as 5 PCHs do Complexo Assungui em 3D para o Google Earth.

Para cada PCH: barragem de concreto (CCR) em degraus, vertedouro de soleira
livre, casa de força, lâmina d'água no NA e APP.
Geometria a partir dos KMZ de reservatório/arranjo do Drive (_ORGANIZADO);
cotas das Fichas-Resumo do Projeto Básico.

Ajuste vertical: o relevo do Google Earth (SRTM) fica 10-25 m acima do terreno
real no fundo desses vales estreitos. Com as cotas reais a barragem ficaria
enterrada e o lago escondido. Por isso toda a geometria em cota absoluta é
deslocada de "ajuste" metros, valor calibrado pela mediana de (relevo SRTM -
NA) ao longo da margem de cada reservatório. As cotas reais vão na descrição.

Uso: python gerar_kmz_3d.py <pasta_com_os_kml_extraidos> <saida.kmz>
"""
import math
import re
import sys
import zipfile
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import substring, unary_union

TO_UTM = Transformer.from_crs(4326, 31982, always_xy=True)  # SIRGAS 2000 / UTM 22S
TO_GEO = Transformer.from_crs(31982, 4326, always_xy=True)

STEP = 1.5      # altura de cada degrau do CCR (m)
SLOPE = 0.8     # paramento de jusante 0,8H:1V
CREST_W = 6.0   # largura da crista da barragem (m)
SPILL_W = 3.0   # largura da crista do vertedouro (m)
CF_ALTURA = 12  # altura aparente da casa de força sobre o terreno (m)

# Coordenadas locais (m) em relação a "origem" (UTM). "eixo" = paramento de
# montante, da ombreira esquerda para a direita; "vert" = trecho do vertedouro
# em distância ao longo do eixo; "cf" = contorno da casa de força.
PCHS = {
    "2B": dict(
        nome="PCH Açungui 2B", mw=12.0, origem=(654100, 7240500),
        fonte="2B_arranjo.kml", na=370.0, crista=374.5, jusante=348.0, ajuste=9,
        eixo=[(-128, 13), (-35, -3), (155, 130)], vert=(95, 225),
        cf=[(55, 112), (70, 128), (83, 113), (68, 97)],
    ),
    "2C": dict(
        nome="PCH Açungui 2C", mw=13.1, origem=(644500, 7227550),
        fonte="2C_reservatorio.kml", na=450.0, crista=456.5, jusante=415.0, ajuste=13,
        eixo=[(66, -96), (140, 92)], vert=(58, 138),
        cf=[(153, 33), (160, 20), (187, 48), (180, 60)],
    ),
    "2D": dict(
        nome="PCH Açungui 2D", mw=12.0, origem=(642440, 7225620),
        fonte="2D_reservatorio.kml", na=484.0, crista=488.7, jusante=450.0, ajuste=16,
        eixo=[(-128, 25), (108, -20)], vert=(40, 120),
        cf=[(10, 32), (13, 47), (42, 42), (39, 27)],
    ),
    "2E": dict(
        nome="PCH Açungui 2E", mw=5.94, origem=(643570, 7219000),
        fonte="2E_arranjo.kml", na=502.0, crista=506.4, jusante=484.5, ajuste=20,
        eixo=[(-84, -34), (28, -3), (80, 1)], vert=(22, 102),
        cf=[(30, -2), (46, -2), (46, 42), (30, 42)],
    ),
    "2F": dict(
        nome="PCH Açungui 2F", mw=9.9, origem=(645120, 7216880),
        fonte="2F_arranjo.kml", na=534.5, crista=538.5, jusante=502.3, ajuste=20,
        eixo=[(-22, -55), (-8, -42), (8, -25), (18, -5), (22, 15), (22, 32),
              (25, 62), (18, 100)], vert=(19, 102),
        cf=[(-20, 32), (-20, 60), (2, 60), (2, 32)],
    ),
}

STYLES = """
<Style id="reservatorio"><LineStyle><color>33000000</color><width>3</width></LineStyle>
  <PolyStyle><color>66ffaa55</color></PolyStyle></Style>
<Style id="lamina"><LineStyle><color>00000000</color><width>0</width></LineStyle>
  <PolyStyle><color>99ffaa55</color><outline>0</outline></PolyStyle></Style>
<Style id="app"><LineStyle><color>66000000</color><width>3</width></LineStyle>
  <PolyStyle><color>667fffff</color></PolyStyle></Style>
<Style id="concreto_a"><LineStyle><color>ff5a5a5a</color><width>1</width></LineStyle>
  <PolyStyle><color>ffdedede</color></PolyStyle></Style>
<Style id="concreto_b"><LineStyle><color>ff5a5a5a</color><width>1</width></LineStyle>
  <PolyStyle><color>ffbdbdbd</color></PolyStyle></Style>
<Style id="vertedouro_a"><LineStyle><color>ff6e6e6e</color><width>1</width></LineStyle>
  <PolyStyle><color>fff5f0e8</color></PolyStyle></Style>
<Style id="vertedouro_b"><LineStyle><color>ff6e6e6e</color><width>1</width></LineStyle>
  <PolyStyle><color>ffd6d0c8</color></PolyStyle></Style>
<Style id="casa_forca"><LineStyle><color>ff3c3c3c</color><width>1</width></LineStyle>
  <PolyStyle><color>ff5f7fa8</color></PolyStyle></Style>
<Style id="rotulo"><IconStyle><scale>1.1</scale><Icon>
  <href>http://maps.google.com/mapfiles/kml/shapes/water.png</href></Icon></IconStyle>
  <LabelStyle><scale>1.1</scale></LabelStyle></Style>
"""


def read_kml(path):
    """Lista (estilo, nome, tipo, [pontos UTM]) de todos os Placemarks."""
    s = Path(path).read_text(encoding="utf-8", errors="replace")
    out = []
    for p in re.findall(r"<Placemark>(.*?)</Placemark>", s, re.S):
        nm = re.search(r"<name>(.*?)</name>", p, re.S)
        st = re.search(r"<styleUrl>#?(.*?)</styleUrl>", p)
        for g in re.finditer(r"<(Polygon|LineString)>(.*?)</\1>", p, re.S):
            c = re.search(r"<coordinates>(.*?)</coordinates>", g.group(2), re.S)
            pts = [tuple(map(float, q.split(",")[:2])) for q in c.group(1).split()]
            utm = [TO_UTM.transform(x, y) for x, y in pts]
            out.append((st.group(1) if st else "", nm.group(1) if nm else "", g.group(1), utm))
    return out


def lagos_e_app(cod, feats):
    """Polígonos do reservatório e da APP (APP sem a área alagada)."""
    if cod == "2C":
        # 2C (reestudo): contornos vêm como polilinhas que fecham em anel
        lines = {st: pts for st, _, g, pts in feats if g == "LineString"}
        res = Polygon(lines["line311"] + lines["line312"]).buffer(0)
        chain = ["line265", "line261", "line243", "line246", "line253", "line258",
                 "line267", "line256", "line244", "line273", "line277", "line2600"]
        outer = Polygon([p for k in chain for p in lines[k]]).buffer(0)
        return res, outer.difference(res)
    res = unary_union([Polygon(pts).buffer(0) for st, _, g, pts in feats
                       if g == "Polygon" and "RESERVAT" in st.upper()])
    app = unary_union([Polygon(pts).buffer(0) for st, _, g, pts in feats
                       if g == "Polygon" and "APP" in st.upper()])
    return res, app.difference(res)


def polys(geom):
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def coords(ring, z=None):
    out = []
    for x, y in ring:
        lon, lat = TO_GEO.transform(x, y)
        out.append(f"{lon:.7f},{lat:.7f}" + (f",{z:.2f}" if z is not None else ""))
    return " ".join(out)


def kml_polygon(poly, style, z=None, extrude=False, name=None, mode="absolute"):
    """z=None: polígono colado no terreno; senão cota em `mode`."""
    alt = (f"<altitudeMode>{mode}</altitudeMode>" if z is not None
           else "<tessellate>1</tessellate>")
    ext = "<extrude>1</extrude>" if extrude else ""
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{coords(r.coords, z)}</coordinates>"
        f"</LinearRing></innerBoundaryIs>" for r in poly.interiors)
    nm = f"<name>{name}</name>" if name else ""
    return (f"<Placemark>{nm}<styleUrl>#{style}</styleUrl><Polygon>{ext}{alt}"
            f"<outerBoundaryIs><LinearRing><coordinates>{coords(poly.exterior.coords, z)}"
            f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon></Placemark>")


def downstream_sign(axis, reservoir):
    """+1 se jusante fica à esquerda do eixo (offset positivo), senão -1."""
    left = axis.offset_curve(15).intersection(reservoir).length
    right = axis.offset_curve(-15).intersection(reservoir).length
    return -1 if left > right else 1


def strip(axis, sign, d0, d1):
    """Faixa entre as paralelas ao eixo a d0 e d1 metros para jusante."""
    a = axis if d0 == 0 else axis.offset_curve(sign * d0)
    b = axis.offset_curve(sign * d1)
    return Polygon(list(a.coords) + list(b.coords)[::-1]).buffer(0)


def stepped_block(axis, sign, top, crest_w, base, prefix):
    """Crista + degraus do paramento de jusante, cada faixa extrudada até o terreno."""
    parts = [kml_polygon(strip(axis, sign, 0, crest_w), f"{prefix}_a", top, True)]
    n = max(1, math.ceil((top - base) / STEP))
    for i in range(n):
        z = top - (i + 1) * STEP
        d0 = crest_w + SLOPE * i * STEP
        d1 = crest_w + SLOPE * (i + 1) * STEP
        parts.append(kml_polygon(strip(axis, sign, d0, d1),
                                 f"{prefix}_{'b' if i % 2 == 0 else 'a'}", z, True))
    return parts


def heading(axis, sign):
    """Rumo da câmera olhando a barragem a partir de jusante."""
    (x0, y0), (x1, y1) = axis.coords[0], axis.coords[-1]
    ax, ay = x1 - x0, y1 - y0
    nx, ny = (-ay, ax) if sign > 0 else (ay, -ax)  # aponta para jusante
    return math.degrees(math.atan2(-nx, -ny)) % 360


def build_pch(cod, cfg, src_dir):
    feats = read_kml(Path(src_dir) / cfg["fonte"])
    res, app = lagos_e_app(cod, feats)
    ox, oy = cfg["origem"]
    axis = LineString([(ox + x, oy + y) for x, y in cfg["eixo"]])
    sign = downstream_sign(axis, res)
    s1, s2 = cfg["vert"]
    dz = cfg["ajuste"]
    crista, na = cfg["crista"] + dz, cfg["na"] + dz
    base = cfg["jusante"] + dz - 4.0

    barragem = []
    for a, b in [(0, s1), (s2, axis.length)]:
        if b - a > 1:
            barragem += stepped_block(substring(axis, a, b), sign, crista, CREST_W,
                                      base, "concreto")
    vertedouro = stepped_block(substring(axis, s1, s2), sign, na, SPILL_W, base,
                               "vertedouro")
    cf = Polygon([(ox + x, oy + y) for x, y in cfg["cf"]])
    casa = [kml_polygon(cf, "casa_forca", CF_ALTURA, True, "Casa de força",
                        "relativeToGround")]

    # o lago encosta no paramento de montante: corta o que invade a barragem
    dam_foot = strip(axis, sign, 0, CREST_W + SLOPE * (crista - base) + 1)
    lago = res.difference(dam_foot).simplify(0.5)
    app = app.difference(dam_foot).simplify(0.5)

    mid = axis.interpolate(0.5, normalized=True)
    lon, lat = TO_GEO.transform(mid.x, mid.y)
    desc = (f"Potência: {cfg['mw']:.2f} MW<br/>NA máx. normal: {cfg['na']:.2f} m<br/>"
            f"Crista: {cfg['crista']:.2f} m<br/>Vertedouro de soleira livre: "
            f"{s2 - s1:.0f} m<br/><br/><i>Modelo ilustrativo: geometria elevada "
            f"{dz} m para acompanhar o relevo do Google Earth.</i>")
    look = (f"<LookAt><longitude>{lon:.6f}</longitude><latitude>{lat:.6f}</latitude>"
            f"<altitude>{crista:.0f}</altitude><heading>{heading(axis, sign):.0f}"
            f"</heading><tilt>62</tilt><range>650</range>"
            f"<altitudeMode>absolute</altitudeMode></LookAt>")
    rotulo = (f"<Placemark><name>{cfg['nome']}</name><description><![CDATA[{desc}]]>"
              f"</description>{look}<styleUrl>#rotulo</styleUrl><Point>"
              f"<altitudeMode>relativeToGround</altitudeMode><coordinates>{lon:.7f},"
              f"{lat:.7f},60</coordinates></Point></Placemark>")

    def folder(name, items, visible=True):
        return (f"<Folder><name>{name}</name><visibility>{int(visible)}</visibility>"
                + "".join(items) + "</Folder>")

    return (f"<Folder><name>{cfg['nome']}</name>{look}" + rotulo
            + folder("Barragem 3D", barragem + vertedouro + casa)
            + folder("Lâmina d'água 3D (NA)", [kml_polygon(p, "lamina", na, False,
                                                            "Lâmina d'água") for p in polys(lago)])
            + folder("Área alagada", [kml_polygon(p, "reservatorio", None, False,
                                                  "Área alagada") for p in polys(lago)])
            + folder("APP", [kml_polygon(p, "app", None, False, "APP") for p in polys(app)])
            + "</Folder>")


def main(src_dir, out):
    body = "".join(build_pch(c, cfg, src_dir) for c, cfg in PCHS.items())
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           "<name>Complexo Assungui - PCHs em 3D</name><open>1</open>"
           + STYLES + body + "</Document></kml>")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
    print(f"{out}: {Path(out).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
