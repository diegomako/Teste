"""Gera um KMZ com as 5 PCHs do Complexo Assungui em 3D para o Google Earth.

Para cada PCH: barragem de concreto (CCR), vertedouro em degraus, casa de
força, lâmina d'água no NA e APP. Barragem e casa de força são um modelo
COLLADA (.dae) sólido e sombreado; água e APP são polígonos KML.
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

STEP = 1.2      # altura de cada degrau do vertedouro (m)
SLOPE = 0.8     # paramento de jusante 0,8H:1V
CREST_W = 6.0   # largura da crista da barragem (m)
SPILL_W = 3.0   # largura da crista do vertedouro (m)
FOOT = 8.0      # quanto a base do modelo desce abaixo do NA de jusante (fica sob o terreno)

# Coordenadas locais (m) em relação a "origem" (UTM). "eixo" = paramento de
# montante, da ombreira esquerda para a direita; "vert" = trecho do vertedouro
# em distância ao longo do eixo; "cf" = contorno da casa de força, com base e
# topo na cota do relevo do Google Earth (já incluem o ajuste).
PCHS = {
    "2B": dict(
        nome="PCH Açungui 2B", mw=12.0, origem=(654100, 7240500),
        fonte="2B_arranjo.kml", na=370.0, crista=374.5, jusante=348.0, ajuste=9,
        eixo=[(-128, 13), (-35, -3), (155, 130)], vert=(95, 225),
        cf=[(55, 112), (70, 128), (83, 113), (68, 97)], cf_cotas=(361, 380),
    ),
    "2C": dict(
        nome="PCH Açungui 2C", mw=13.1, origem=(644500, 7227550),
        fonte="2C_reservatorio.kml", na=450.0, crista=456.5, jusante=415.0, ajuste=13,
        eixo=[(66, -96), (140, 92)], vert=(58, 138),
        cf=[(153, 33), (160, 20), (187, 48), (180, 60)], cf_cotas=(449, 474),
    ),
    "2D": dict(
        nome="PCH Açungui 2D", mw=12.0, origem=(642440, 7225620),
        fonte="2D_reservatorio.kml", na=484.0, crista=488.7, jusante=450.0, ajuste=16,
        eixo=[(-128, 25), (108, -20)], vert=(40, 120),
        cf=[(10, 32), (13, 47), (42, 42), (39, 27)], cf_cotas=(471, 490),
    ),
    "2E": dict(
        nome="PCH Açungui 2E", mw=5.94, origem=(643570, 7219000),
        fonte="2E_arranjo.kml", na=502.0, crista=506.4, jusante=484.5, ajuste=20,
        eixo=[(-84, -34), (28, -3), (80, 1), (140, 6)], vert=(22, 102),
        cf=[(30, -2), (46, -2), (46, 42), (30, 42)], cf_cotas=(503, 521),
    ),
    "2F": dict(
        nome="PCH Açungui 2F", mw=9.9, origem=(645120, 7216880),
        fonte="2F_arranjo.kml", na=534.5, crista=538.5, jusante=502.3, ajuste=20,
        eixo=[(-31, -63), (-22, -55), (-8, -42), (8, -25), (18, -5), (22, 15), (22, 32),
              (25, 62), (18, 100)], vert=(31, 114),
        cf=[(-20, 32), (-20, 60), (2, 60), (2, 32)], cf_cotas=(528, 550),
    ),
}

# cores difusas RGB dos materiais do modelo
MATERIAIS = {
    "concreto": (0.80, 0.80, 0.78),
    "crista": (0.90, 0.90, 0.88),
    "vertedouro": (0.92, 0.93, 0.93),
    "parede_cf": (0.82, 0.78, 0.70),
    "telhado_cf": (0.55, 0.32, 0.25),
}

STYLES = """
<Style id="reservatorio"><LineStyle><color>33000000</color><width>3</width></LineStyle>
  <PolyStyle><color>66ffaa55</color></PolyStyle></Style>
<Style id="lamina"><LineStyle><color>00000000</color><width>0</width></LineStyle>
  <PolyStyle><color>99ffaa55</color><outline>0</outline></PolyStyle></Style>
<Style id="app"><LineStyle><color>66000000</color><width>3</width></LineStyle>
  <PolyStyle><color>667fffff</color></PolyStyle></Style>
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


def kml_polygon(poly, style, z=None, name=None):
    """z=None: polígono colado no terreno; senão plano na cota absoluta z."""
    alt = ("<altitudeMode>absolute</altitudeMode>" if z is not None
           else "<tessellate>1</tessellate>")
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{coords(r.coords, z)}</coordinates>"
        f"</LinearRing></innerBoundaryIs>" for r in poly.interiors)
    nm = f"<name>{name}</name>" if name else ""
    return (f"<Placemark>{nm}<styleUrl>#{style}</styleUrl><Polygon>{alt}"
            f"<outerBoundaryIs><LinearRing><coordinates>{coords(poly.exterior.coords, z)}"
            f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon></Placemark>")


def downstream_sign(axis, reservoir):
    """+1 se jusante fica à esquerda do eixo (offset positivo), senão -1."""
    left = axis.offset_curve(15).intersection(reservoir).length
    right = axis.offset_curve(-15).intersection(reservoir).length
    return -1 if left > right else 1


def heading(axis, sign):
    """Rumo da câmera olhando a barragem a partir de jusante."""
    (x0, y0), (x1, y1) = axis.coords[0], axis.coords[-1]
    ax, ay = x1 - x0, y1 - y0
    nx, ny = (-ay, ax) if sign > 0 else (ay, -ax)  # aponta para jusante
    return math.degrees(math.atan2(-nx, -ny)) % 360


class Mesh:
    """Triângulos por material, em metros (x leste, y norte, z cota)."""

    def __init__(self):
        self.tris = {m: [] for m in MATERIAIS}

    def quad(self, mat, a, b, c, d, want):
        """Quadrilátero a-b-c-d com a normal virada para o vetor `want`."""
        n = _normal(a, b, c)
        if sum(i * j for i, j in zip(n, want)) < 0:
            a, b, c, d = d, c, b, a
        self.tris[mat] += [(a, b, c), (a, c, d)]


def _normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    s = math.sqrt(sum(i * i for i in n)) or 1.0
    return tuple(i / s for i in n)


def sweep(mesh, pts, sign, columns, mat, caps=(True, True)):
    """Varre a seção transversal ao longo do eixo `pts` (lista de (x, y)).

    columns: lista de (d0, d1, z0, z1, material_topo) — faixas da seção, com a
    distância d para jusante e a cota do topo em d0 e d1; a base é columns[0]
    ... até `base` (cota inferior comum, guardada em columns como z mínimo).
    """
    base = min(min(c[2], c[3]) for c in columns)
    m = len(pts)
    # normais de jusante nos vértices, com mitra nas quinas
    seg = []
    for i in range(m - 1):
        dx, dy = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        L = math.hypot(dx, dy)
        seg.append((-dy / L * sign, dx / L * sign))
    nrm = []
    for i in range(m):
        a = seg[max(i - 1, 0)]
        b = seg[min(i, m - 2)]
        nx, ny = a[0] + b[0], a[1] + b[1]
        L = math.hypot(nx, ny)
        nx, ny = nx / L, ny / L
        miter = 1 / max(0.3, nx * b[0] + ny * b[1])
        nrm.append((nx * miter, ny * miter))

    def P(i, d, z):
        return (pts[i][0] + nrm[i][0] * d, pts[i][1] + nrm[i][1] * d, z)

    for i in range(m - 1):
        out = (nrm[i][0] + nrm[i + 1][0], nrm[i][1] + nrm[i + 1][1], 0)
        up_face = (-out[0], -out[1], 0)
        # paramento de montante (vertical)
        z = columns[0][2]
        mesh.quad(mat, P(i, 0, base), P(i + 1, 0, base), P(i + 1, 0, z), P(i, 0, z), up_face)
        for k, (d0, d1, z0, z1, mtop) in enumerate(columns):
            mesh.quad(mtop, P(i, d0, z0), P(i + 1, d0, z0), P(i + 1, d1, z1), P(i, d1, z1),
                      (0, 0, 1))
            zn = columns[k + 1][2] if k + 1 < len(columns) else base
            if zn != z1:  # espelho do degrau / face final de jusante
                mesh.quad(mat, P(i, d1, z1), P(i + 1, d1, z1), P(i + 1, d1, zn), P(i, d1, zn),
                          out)
    for i, on, t in ((0, caps[0], -1), (m - 1, caps[1], 1)):
        if not on:
            continue
        j = 1 if i == 0 else m - 2
        tang = ((pts[i][0] - pts[j][0]) * 1.0, (pts[i][1] - pts[j][1]) * 1.0, 0)
        for d0, d1, z0, z1, _ in columns:
            mesh.quad(mat, P(i, d0, base), P(i, d1, base), P(i, d1, z1), P(i, d0, z0), tang)


def dam_columns(top, crest_w, base):
    """Barragem não vertente: crista + paramento liso 0,8H:1V."""
    return [(0, crest_w, top, top, "crista"),
            (crest_w, crest_w + SLOPE * (top - base), top, base, "concreto")]


def spill_columns(top, crest_w, base):
    """Vertedouro de soleira livre com degraus."""
    cols = [(0, crest_w, top, top, "vertedouro")]
    n = max(1, math.ceil((top - base) / STEP))
    for i in range(n):
        z = max(base, top - (i + 1) * STEP)
        d0 = crest_w + SLOPE * STEP * i
        cols.append((d0, d0 + SLOPE * STEP, z, z, "vertedouro"))
    return cols


def box(mesh, ring, z0, z1):
    """Casa de força: prisma com paredes e telhado."""
    pts = list(ring)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        out = ((a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy, 0)
        mesh.quad("parede_cf", (*a, z0), (*b, z0), (*b, z1), (*a, z1), out)
    mesh.tris["telhado_cf"] += [((*pts[0], z1), (*pts[i], z1), (*pts[i + 1], z1))
                                for i in range(1, len(pts) - 1)]
    tri = mesh.tris["telhado_cf"]
    for k in range(len(tri) - len(pts) + 2, len(tri)):
        if _normal(*tri[k])[2] < 0:
            tri[k] = tri[k][::-1]


def collada(mesh, ox, oy):
    """Documento COLLADA com a malha em metros relativos à origem (ox, oy)."""
    mats, geoms, nodes = [], [], []
    for name, rgb in MATERIAIS.items():
        tris = mesh.tris[name]
        if not tris:
            continue
        pos, nor = [], []
        for t in tris:
            n = _normal(*t)
            for x, y, z in t:
                pos += [x - ox, y - oy, z]
                nor += n
        cnt = len(tris) * 3
        idx = " ".join(f"{i} {i}" for i in range(cnt))
        mats.append(
            f'<effect id="{name}-fx"><profile_COMMON><technique sid="c"><lambert>'
            f'<diffuse><color>{rgb[0]} {rgb[1]} {rgb[2]} 1</color></diffuse>'
            f'</lambert></technique><extra><technique profile="GOOGLEEARTH">'
            f'<double_sided>1</double_sided></technique></extra></profile_COMMON></effect>')
        geoms.append(
            f'<geometry id="{name}-g"><mesh>'
            f'<source id="{name}-p"><float_array id="{name}-pa" count="{len(pos)}">'
            + " ".join(f"{v:.3f}" for v in pos) +
            f'</float_array><technique_common><accessor source="#{name}-pa" count="{cnt}" '
            f'stride="3"><param name="X" type="float"/><param name="Y" type="float"/>'
            f'<param name="Z" type="float"/></accessor></technique_common></source>'
            f'<source id="{name}-n"><float_array id="{name}-na" count="{len(nor)}">'
            + " ".join(f"{v:.4f}" for v in nor) +
            f'</float_array><technique_common><accessor source="#{name}-na" count="{cnt}" '
            f'stride="3"><param name="X" type="float"/><param name="Y" type="float"/>'
            f'<param name="Z" type="float"/></accessor></technique_common></source>'
            f'<vertices id="{name}-v"><input semantic="POSITION" source="#{name}-p"/>'
            f'</vertices><triangles material="{name}-m" count="{len(tris)}">'
            f'<input semantic="VERTEX" source="#{name}-v" offset="0"/>'
            f'<input semantic="NORMAL" source="#{name}-n" offset="1"/><p>{idx}</p>'
            f'</triangles></mesh></geometry>')
        nodes.append(
            f'<instance_geometry url="#{name}-g"><bind_material><technique_common>'
            f'<instance_material symbol="{name}-m" target="#{name}-mat"/>'
            f'</technique_common></bind_material></instance_geometry>')
    materials = "".join(f'<material id="{n}-mat"><instance_effect url="#{n}-fx"/></material>'
                        for n in MATERIAIS if mesh.tris[n])
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
            '<asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>'
            f'<library_effects>{"".join(mats)}</library_effects>'
            f'<library_materials>{materials}</library_materials>'
            f'<library_geometries>{"".join(geoms)}</library_geometries>'
            '<library_visual_scenes><visual_scene id="s"><node id="barragem">'
            + "".join(nodes) +
            '</node></visual_scene></library_visual_scenes>'
            '<scene><instance_visual_scene url="#s"/></scene></COLLADA>')


def build_pch(cod, cfg, src_dir):
    """Devolve (kml da pasta da PCH, conteúdo do .dae)."""
    feats = read_kml(Path(src_dir) / cfg["fonte"])
    res, app = lagos_e_app(cod, feats)
    ox, oy = cfg["origem"]
    axis = LineString([(ox + x, oy + y) for x, y in cfg["eixo"]])
    sign = downstream_sign(axis, res)
    s1, s2 = cfg["vert"]
    dz = cfg["ajuste"]
    crista, na = cfg["crista"] + dz, cfg["na"] + dz
    base = cfg["jusante"] + dz - FOOT

    mesh = Mesh()
    if s1 > 1:
        sweep(mesh, list(substring(axis, 0, s1).coords), sign,
              dam_columns(crista, CREST_W, base), "concreto")
    if axis.length - s2 > 1:
        sweep(mesh, list(substring(axis, s2, axis.length).coords), sign,
              dam_columns(crista, CREST_W, base), "concreto")
    # as pontas do vertedouro ficam encostadas nos blocos da barragem
    sweep(mesh, list(substring(axis, s1, s2).coords), sign,
          spill_columns(na, SPILL_W, base), "vertedouro", caps=(s1 <= 1, False))
    box(mesh, [(ox + x, oy + y) for x, y in cfg["cf"]], *cfg["cf_cotas"])
    dae = collada(mesh, ox, oy)

    # o lago encosta no paramento de montante: corta o que invade a barragem
    foot = Polygon(list(axis.coords) + list(
        axis.offset_curve(sign * (CREST_W + SLOPE * (crista - base) + 1)).coords)[::-1]).buffer(0)
    lago = res.difference(foot).simplify(0.5)
    app = app.difference(foot).simplify(0.5)

    olon, olat = TO_GEO.transform(ox, oy)
    modelo = (f"<Placemark><name>Barragem e casa de força</name><Model>"
              f"<altitudeMode>absolute</altitudeMode><Location><longitude>{olon:.8f}"
              f"</longitude><latitude>{olat:.8f}</latitude><altitude>0</altitude></Location>"
              f"<Orientation><heading>{grid_convergence(ox, oy):.4f}</heading><tilt>0</tilt>"
              f"<roll>0</roll></Orientation><Scale><x>1</x><y>1</y><z>1</z></Scale>"
              f"<Link><href>modelos/{cod}.dae</href></Link></Model></Placemark>")

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

    def folder(name, items):
        return f"<Folder><name>{name}</name>" + "".join(items) + "</Folder>"

    kml = (f"<Folder><name>{cfg['nome']}</name>{look}" + rotulo
           + folder("Barragem 3D", [modelo])
           + folder("Lâmina d'água 3D (NA)", [kml_polygon(p, "lamina", na, "Lâmina d'água")
                                               for p in polys(lago)])
           + folder("Área alagada", [kml_polygon(p, "reservatorio", None, "Área alagada")
                                     for p in polys(lago)])
           + folder("APP", [kml_polygon(p, "app", None, "APP") for p in polys(app)])
           + "</Folder>")
    return kml, dae


def grid_convergence(x, y):
    """Ângulo (graus) entre o norte da quadrícula UTM e o norte verdadeiro.

    A malha é montada em coordenadas UTM; o Google Earth posiciona o modelo
    em leste/norte verdadeiros, então ele é girado por este ângulo.
    """
    lon0, lat0 = TO_GEO.transform(x, y)
    lon1, lat1 = TO_GEO.transform(x, y + 100)
    dx = (lon1 - lon0) * math.cos(math.radians(lat0))
    return math.degrees(math.atan2(dx, lat1 - lat0))


def main(src_dir, out):
    pastas, modelos = [], {}
    for cod, cfg in PCHS.items():
        kml, dae = build_pch(cod, cfg, src_dir)
        pastas.append(kml)
        modelos[cod] = dae
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           "<name>Complexo Assungui - PCHs em 3D</name><open>1</open>"
           + STYLES + "".join(pastas) + "</Document></kml>")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        for cod, dae in modelos.items():
            z.writestr(f"modelos/{cod}.dae", dae)
    print(f"{out}: {Path(out).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
