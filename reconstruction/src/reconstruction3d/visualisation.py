from __future__ import annotations

"""Creation de la vue 3D HTML interactive."""

import json
from pathlib import Path

import numpy as np


def sauver_html_3d(chemin: Path, titre: str, points: np.ndarray, couleurs: np.ndarray | None = None) -> None:
    points_affiches = points
    couleurs_affichees = couleurs
    if len(points_affiches) > 70000:
        indices = np.linspace(0, len(points_affiches) - 1, 70000, dtype=int)
        points_affiches = points_affiches[indices]
        if couleurs_affichees is not None:
            couleurs_affichees = couleurs_affichees[indices]

    points_centres = points_affiches - points_affiches.mean(axis=0)
    echelle = float(np.max(np.ptp(points_centres, axis=0)))
    z_min, z_max = np.percentile(points_centres[:, 2], [1, 99])
    donnees = [[round(float(x), 3), round(float(y), 3), round(float(z), 3)] for x, y, z in points_centres]
    donnees_couleurs = None
    if couleurs_affichees is not None and len(couleurs_affichees) == len(points_affiches):
        couleurs_uint8 = np.clip(couleurs_affichees, 0, 255).astype(np.uint8)
        donnees_couleurs = couleurs_uint8.tolist()
    bouton_couleur = (
        '<button id="modeBtn" type="button">Mode couleur</button>'
        if donnees_couleurs is not None
        else '<span id="noColor">Pas d image couleur</span>'
    )

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{titre} - vue 3D</title>
<style>
html, body {{ margin:0; height:100%; overflow:hidden; background:#101114; color:#f2f2f2; font-family:Arial, sans-serif; }}
#hud {{ position:fixed; left:14px; top:12px; background:rgba(0,0,0,.55); padding:10px 12px; border-radius:6px; font-size:13px; line-height:1.4; }}
#modePanel {{ position:fixed; right:14px; top:12px; background:rgba(0,0,0,.55); padding:10px 12px; border-radius:6px; }}
#modeBtn {{ border:1px solid rgba(255,255,255,.35); background:#f2f2f2; color:#101114; padding:8px 12px; border-radius:4px; font-size:13px; cursor:pointer; }}
#modeBtn.active {{ background:#37b36b; color:#fff; border-color:#37b36b; }}
#noColor {{ color:#cfcfcf; font-size:13px; }}
canvas {{ display:block; width:100vw; height:100vh; cursor:grab; }}
canvas:active {{ cursor:grabbing; }}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud">{titre}<br>Souris: tourner | molette: zoom | double clic: reset<br>Points: {len(donnees)}</div>
<div id="modePanel">{bouton_couleur}</div>
<script>
const points = {json.dumps(donnees)};
const pointColors = {json.dumps(donnees_couleurs)};
const baseScale = {echelle};
const zMin = {float(z_min)};
const zMax = {float(z_max)};
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
let rx = -0.85, ry = 0.0, rz = 0.02, zoom = 0.9;
let dragging = false, lx = 0, ly = 0;
let colorMode = !!pointColors;
function resize() {{ canvas.width = innerWidth * devicePixelRatio; canvas.height = innerHeight * devicePixelRatio; draw(); }}
function rot(p) {{
  let [x,y,z] = p;
  let cy=Math.cos(ry), sy=Math.sin(ry), cx=Math.cos(rx), sx=Math.sin(rx), cz=Math.cos(rz), sz=Math.sin(rz);
  let x1=x*cy+z*sy, z1=-x*sy+z*cy, y1=y;
  let y2=y1*cx-z1*sx, z2=y1*sx+z1*cx, x2=x1;
  return [x2*cz-y2*sz, x2*sz+y2*cz, z2];
}}
function color(t) {{
  t = Math.max(0, Math.min(1, t));
  const r = Math.round(255*Math.min(1, Math.max(0, 1.5-Math.abs(4*t-3))));
  const g = Math.round(255*Math.min(1, Math.max(0, 1.5-Math.abs(4*t-2))));
  const b = Math.round(255*Math.min(1, Math.max(0, 1.5-Math.abs(4*t-1))));
  return `rgb(${{r}},${{g}},${{b}})`;
}}
function draw() {{
  const w=canvas.width, h=canvas.height;
  ctx.fillStyle='#101114'; ctx.fillRect(0,0,w,h);
  const s = Math.min(w,h) * zoom / baseScale;
  const projected = points.map((p, i) => {{ const q=rot(p); return [w/2+q[0]*s, h/2-q[1]*s, q[2], p[2], i]; }}).sort((a,b)=>a[2]-b[2]);
  const px = Math.max(2.8, 4.0 * devicePixelRatio);
  for (const p of projected) {{
    if (colorMode && pointColors) {{
      const c = pointColors[p[4]];
      ctx.fillStyle = `rgb(${{c[0]}},${{c[1]}},${{c[2]}})`;
    }} else {{
      ctx.fillStyle = color((p[3]-zMin)/(zMax-zMin || 1));
    }}
    ctx.fillRect(p[0], p[1], px, px);
  }}
}}
const modeBtn = document.getElementById('modeBtn');
if (modeBtn) {{
  modeBtn.classList.toggle('active', colorMode);
  modeBtn.textContent = colorMode ? 'Mode hauteur' : 'Mode couleur';
  modeBtn.addEventListener('click', () => {{
    colorMode = !colorMode;
    modeBtn.classList.toggle('active', colorMode);
    modeBtn.textContent = colorMode ? 'Mode hauteur' : 'Mode couleur';
    draw();
  }});
}}
canvas.addEventListener('mousedown', e => {{ dragging=true; lx=e.clientX; ly=e.clientY; }});
addEventListener('mouseup', () => dragging=false);
addEventListener('mousemove', e => {{ if(!dragging) return; ry += (e.clientX-lx)*0.006; rx += (e.clientY-ly)*0.006; lx=e.clientX; ly=e.clientY; draw(); }});
canvas.addEventListener('wheel', e => {{ e.preventDefault(); zoom *= Math.exp(-e.deltaY*0.001); draw(); }}, {{passive:false}});
canvas.addEventListener('dblclick', () => {{ rx=-0.85; ry=0; rz=0.02; zoom=0.9; draw(); }});
addEventListener('resize', resize);
resize();
</script>
</body>
</html>"""
    chemin.write_text(html, encoding="utf-8")
