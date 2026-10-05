"""
Procedural Signage & 3D Department Board Generator for Isaac Sim
================================================================
Generates high-contrast, professional hospital department signage textures using PIL
and binds them to USD PreviewSurface materials on 3D doorway signboards and
overhead floating room nameboards with explicit UV texture coordinates.

Features:
- High-resolution 1024x256 32-bit RGBA textures with bold typographic hierarchy
- Glowing neon color-coded borders and emissive self-illuminated materials
- Explicit UsdGeom.Mesh quad generation with 'primvars:st' UV mapping
- Prominently visible from isometric camera overview and corridor doorways
- Full coverage for all 28+ clinical departments in the grand hospital layout
"""

from __future__ import annotations

import os
from typing import Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
    HAS_USD = True
except ImportError:
    Gf = Sdf = Usd = UsdGeom = UsdShade = None
    HAS_USD = False

# ─────────────────────────────────────────────────────────────────────────────
# Complete Department Configuration (28+ Clinical Zones)
# ─────────────────────────────────────────────────────────────────────────────

DEPARTMENT_SIGN_CONFIG: dict[str, dict] = {
    # ── North Wing (Surgical & Critical Facilities) ──
    "OT-01": {
        "title": "OPERATING THEATER 1",
        "code": "GENERAL & ORTHOPEDIC SURGERY",
        "border": (0, 220, 170),
        "accent": (0, 255, 200),
    },
    "OT-02": {
        "title": "OPERATING THEATER 2",
        "code": "CARDIOTHORACIC & NEUROSURGERY",
        "border": (0, 220, 170),
        "accent": (0, 255, 200),
    },
    "RAD-01": {
        "title": "RADIOLOGY & IMAGING",
        "code": "MRI & MULTI-SLICE CT SCAN",
        "border": (60, 150, 240),
        "accent": (100, 190, 255),
    },
    "LAB-01": {
        "title": "PATHOLOGY LABORATORY",
        "code": "BIOCHEMISTRY & DIAGNOSTICS",
        "border": (40, 120, 210),
        "accent": (80, 170, 255),
    },
    "BLB-01": {
        "title": "BLOOD BANK & STORAGE",
        "code": "TRANSFUSION MEDICINE",
        "border": (220, 40, 90),
        "accent": (255, 80, 130),
    },
    "PHM-01": {
        "title": "CENTRAL PHARMACY",
        "code": "AUTOMATED MEDICINE DISPENSARY",
        "border": (150, 90, 230),
        "accent": (190, 140, 255),
    },
    "STR-01": {
        "title": "MEDICINE SECURE STORAGE",
        "code": "PHARMACEUTICAL VAULT",
        "border": (180, 140, 100),
        "accent": (220, 180, 140),
    },
    "CHG-01": {
        "title": "ROBOT CHARGING STATION",
        "code": "AMR FLEET DOCKS 1 - 4",
        "border": (0, 200, 245),
        "accent": (0, 245, 255),
    },
    "CHG-02": {
        "title": "AUXILIARY CHARGING DOCK",
        "code": "FAST CHARGE & MAINTENANCE",
        "border": (0, 200, 245),
        "accent": (0, 245, 255),
    },

    # ── Upper-Mid Wing (Intensive & Specialty Care) ──
    "ICU-01": {
        "title": "INTENSIVE CARE UNIT (ICU)",
        "code": "CRITICAL CARE BEDS 1 - 4",
        "border": (40, 140, 230),
        "accent": (90, 185, 255),
    },
    "SUR-01": {
        "title": "SURGICAL RECOVERY (PACU)",
        "code": "POST-ANESTHESIA CARE UNIT",
        "border": (50, 170, 190),
        "accent": (80, 220, 230),
    },
    "NST-01": {
        "title": "CENTRAL NURSE STATION",
        "code": "CLINICAL COMMAND HUB",
        "border": (0, 190, 170),
        "accent": (0, 245, 215),
    },
    "NST-02": {
        "title": "EAST NURSE SUB-STATION",
        "code": "WARD MONITORING & TRIAGE",
        "border": (0, 190, 170),
        "accent": (0, 245, 215),
    },
    "DOC-01": {
        "title": "CONSULTATION CLINIC 1",
        "code": "INTERNAL MEDICINE & PHYSICIAN",
        "border": (160, 120, 210),
        "accent": (200, 165, 250),
    },
    "DOC-02": {
        "title": "CONSULTATION CLINIC 2",
        "code": "CARDIOLOGY SPECIALIST",
        "border": (160, 120, 210),
        "accent": (200, 165, 250),
    },
    "DOC-03": {
        "title": "CONSULTATION CLINIC 3",
        "code": "NEUROLOGY & ORTHOPEDICS",
        "border": (160, 120, 210),
        "accent": (200, 165, 250),
    },
    "ISO-01": {
        "title": "ISOLATION UNIT",
        "code": "NEGATIVE PRESSURE AIRBORNE WARD",
        "border": (220, 190, 40),
        "accent": (255, 230, 60),
    },

    # ── Mid-South Wing (Emergency & Inpatient Wards) ──
    "EMR-01": {
        "title": "EMERGENCY & TRAUMA",
        "code": "CRITICAL RESUSCITATION BAYS",
        "border": (230, 40, 40),
        "accent": (255, 80, 80),
    },
    "TRM-01": {
        "title": "TRAUMA RESUSCITATION",
        "code": "CRITICAL RED ZONE",
        "border": (230, 40, 40),
        "accent": (255, 80, 80),
    },
    "AMB-01": {
        "title": "AMBULANCE BAY & TRIAGE",
        "code": "EMERGENCY VEHICLE STAGING",
        "border": (230, 70, 40),
        "accent": (255, 100, 70),
    },
    "RCT-01": {
        "title": "MAIN RECEPTION & INFO",
        "code": "PATIENT ADMISSIONS & TRIAGE",
        "border": (40, 160, 220),
        "accent": (80, 200, 255),
    },
    "WAT-01": {
        "title": "CENTRAL WAITING LOUNGE",
        "code": "VISITOR & PATIENT SEATING",
        "border": (100, 145, 180),
        "accent": (140, 185, 220),
    },
    "GW-01": {
        "title": "GENERAL INPATIENT WARD A",
        "code": "INPATIENT BEDS 101 - 108",
        "border": (60, 180, 160),
        "accent": (95, 225, 195),
    },
    "GW-02": {
        "title": "GENERAL INPATIENT WARD B",
        "code": "INPATIENT BEDS 109 - 116",
        "border": (60, 180, 160),
        "accent": (95, 225, 195),
    },

    # ── South Wing (Outpatient, Deluxe Suites, Logistics) ──
    "PAT-01": {
        "title": "DELUXE PATIENT ROOM 101",
        "code": "PRIVATE RECOVERY SUITE",
        "border": (70, 165, 215),
        "accent": (110, 205, 255),
    },
    "PAT-02": {
        "title": "DELUXE PATIENT ROOM 102",
        "code": "PRIVATE RECOVERY SUITE",
        "border": (70, 165, 215),
        "accent": (110, 205, 255),
    },
    "PED-01": {
        "title": "PEDIATRIC WARD & CLINIC",
        "code": "CHILD HEALTH & WELLNESS",
        "border": (230, 145, 40),
        "accent": (255, 185, 60),
    },
    "OPD-01": {
        "title": "OUTPATIENT DEPARTMENT (OPD)",
        "code": "DOCTOR CONSULTATION CUBICLES 1 - 4",
        "border": (210, 75, 150),
        "accent": (255, 110, 190),
    },
    "SAN-01": {
        "title": "BIO-SANITIZATION & STERILE",
        "code": "CENTRAL STERILIZATION (CSSD)",
        "border": (40, 190, 190),
        "accent": (75, 235, 235),
    },
    "WSH-01": {
        "title": "PUBLIC RESTROOMS",
        "code": "HYGIENE & SANITARY SUITE",
        "border": (70, 130, 185),
        "accent": (110, 175, 225),
    },
    "STR-02": {
        "title": "BIOMEDICAL EQUIPMENT DEPOT",
        "code": "WHEELCHAIRS, CARTS & MONITORS",
        "border": (115, 135, 160),
        "accent": (150, 170, 195),
    },
    "ENT-01": {
        "title": "AROGYA MEDICAL CENTER",
        "code": "MAIN HOSPITAL ENTRANCE & ADMISSIONS",
        "border": (0, 180, 220),
        "accent": (0, 220, 255),
    },
    "RCT-01": {
        "title": "CENTRAL ATRIUM & RECEPTION",
        "code": "PATIENT ADMISSIONS & INFORMATION",
        "border": (0, 190, 180),
        "accent": (0, 235, 220),
    },
    "ELV-01": {
        "title": "ELEVATOR LOBBY",
        "code": "LEVEL 1 • INPATIENT TOWERS A & B",
        "border": (100, 160, 220),
        "accent": (140, 200, 255),
    },
    "STAIR-01": {
        "title": "STAIRWAY A",
        "code": "EMERGENCY EGRESS & ROOF ACCESS",
        "border": (160, 160, 170),
        "accent": (200, 200, 210),
    },
    "PHM-01": {
        "title": "CENTRAL PHARMACY",
        "code": "DISPENSARY & ROBOT MEDICINE PICKUP",
        "border": (40, 190, 140),
        "accent": (70, 230, 170),
    },
    "ROB-01": {
        "title": "ROBOT MEDICINE PICKUP",
        "code": "AUTONOMOUS DELIVERY AMR DOCK",
        "border": (0, 210, 240),
        "accent": (0, 255, 255),
    },
    "CHG-01": {
        "title": "AROGYA ROBOT OPERATIONS",
        "code": "FLEET CHARGING DOCKS 1 - 4 & MAINTENANCE",
        "border": (0, 200, 245),
        "accent": (0, 245, 255),
    },
    "ICU-01": {
        "title": "INTENSIVE CARE UNIT (ICU)",
        "code": "CRITICAL CARE MONITORING SUITES 1 - 6",
        "border": (30, 140, 230),
        "accent": (70, 185, 255),
    },
    "WAY-01": {
        "title": "WAYFINDING: NORTH WING",
        "code": "← ICU / SURGERY  |  PHARMACY / LAB →",
        "border": (40, 160, 220),
        "accent": (80, 200, 255),
    },
    "WAY-02": {
        "title": "WAYFINDING: SOUTH WING",
        "code": "← EMERGENCY & TRIAGE  |  OUTPATIENT & WARDS →",
        "border": (220, 90, 50),
        "accent": (255, 120, 80),
    },
    "CAF-01": {
        "title": "STAFF CAFETERIA & LOUNGE",
        "code": "DOCTORS' BREAK & CONFERENCE",
        "border": (190, 145, 95),
        "accent": (230, 185, 135),
    },
    "STF-01": {
        "title": "STAFF ROOM & LOUNGE",
        "code": "MEETING & RELAXATION",
        "border": (190, 145, 95),
        "accent": (230, 185, 135),
    },
}

_TEXTURE_CACHE: dict[str, str] = {}


def get_signage_texture_path(room_id: str, output_dir: Optional[str] = None, force_regen: bool = True) -> str:
    """
    Generate or retrieve cached high-resolution (1024x256) 32-bit RGBA PNG texture
    with high-contrast typography and glowing neon borders.
    """
    if not force_regen and room_id in _TEXTURE_CACHE and os.path.exists(_TEXTURE_CACHE[room_id]):
        return _TEXTURE_CACHE[room_id]

    if output_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, "textures", "signage")
    os.makedirs(output_dir, exist_ok=True)

    file_path = os.path.join(output_dir, f"sign_{room_id.replace('-', '_')}.png")

    cfg = DEPARTMENT_SIGN_CONFIG.get(
        room_id,
        {
            "title": room_id.replace("_", " ").upper(),
            "code": "HOSPITAL CLINICAL ZONE",
            "border": (100, 160, 230),
            "accent": (140, 200, 255),
        },
    )

    width, height = 1024, 256
    # Deep obsidian-navy solid background
    img = Image.new("RGBA", (width, height), color=(10, 14, 24, 255))
    draw = ImageDraw.Draw(img)

    border_col = cfg["border"]
    accent_col = cfg["accent"]

    # 1. Subtle Dark Inner Inset
    draw.rectangle([6, 6, width - 7, height - 7], fill=(16, 22, 36, 255))

    # 2. Outer Neon Border (6px thick)
    for b_offset in range(5):
        draw.rectangle(
            [2 + b_offset, 2 + b_offset, width - 3 - b_offset, height - 3 - b_offset],
            outline=border_col,
        )

    # 3. Left Solid Neon Accent Bar (32px wide)
    draw.rectangle([8, 8, 40, height - 9], fill=accent_col)

    # 4. Glowing Top & Bottom Horizontal Accent Stripes
    draw.rectangle([41, 8, width - 9, 16], fill=accent_col)
    draw.rectangle([41, height - 17, width - 9, height - 9], fill=border_col)

    # 5. Fonts (Upgraded to 68pt bold for massive readability from high camera overview)
    font_large = None
    font_sub = None
    font_badge = None

    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for fp in font_paths:
        try:
            font_large = ImageFont.truetype(fp, 68)
            font_sub = ImageFont.truetype(fp.replace("bd", "").replace("b", ""), 28)
            font_badge = ImageFont.truetype(fp, 36)
            break
        except Exception:
            continue

    if font_large is None:
        try:
            font_large = ImageFont.load_default()
            font_sub = font_large
            font_badge = font_large
        except Exception:
            pass

    title = cfg["title"]
    code = cfg["code"]

    # 6. Room Code Pill Badge (Top-Right)
    badge_text = f"[{room_id}]"
    badge_w = 210
    badge_x = width - badge_w - 20
    draw.rectangle([badge_x, 22, width - 20, 78], fill=(24, 34, 54, 255), outline=accent_col, width=2)
    draw.text((badge_x + 16, 28), badge_text, fill=accent_col, font=font_badge)

    # 7. Department Main Title (Huge bold white uppercase text)
    draw.text((58, 28), title, fill=(255, 255, 255, 255), font=font_large)

    # 8. Department Subtitle / Description (Vibrant contrasting text)
    draw.text((60, 148), code, fill=(190, 215, 245, 255), font=font_sub)

    # 9. Medical Cross Icon / Status Dot
    draw.ellipse([width - 50, height - 50, width - 26, height - 26], fill=accent_col)

    # Save as high-quality 32-bit RGBA PNG
    img.save(file_path, format="PNG")
    norm_path = file_path.replace("\\", "/")
    _TEXTURE_CACHE[room_id] = norm_path
    return norm_path



def apply_signage_material(
    stage: Usd.Stage,
    target_prim_path: str,
    room_id: str,
) -> None:
    """
    Create USD PreviewSurface material with the department texture and bind to target prim.
    Both diffuseColor and emissiveColor are connected to ensure self-illumination and clarity.
    """
    if not HAS_USD or stage is None:
        return
    try:
        tex_path = get_signage_texture_path(room_id)
        usd_tex_path = tex_path.replace("\\", "/")
        clean_id = room_id.replace("-", "_")
        mat_prim_path = Sdf.Path(f"/World/Hospital/Materials/SignMat_{clean_id}")

        cfg = DEPARTMENT_SIGN_CONFIG.get(room_id, {})
        border_col = cfg.get("border", (80, 140, 220))
        accent_col = cfg.get("accent", (120, 180, 255))

        material = UsdShade.Material.Define(stage, mat_prim_path)
        shader = UsdShade.Shader.Define(stage, mat_prim_path.AppendChild("PBRShader"))
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.20)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.10)

        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

        # stReader for UV texture coordinates
        st_reader = UsdShade.Shader.Define(stage, mat_prim_path.AppendChild("stReader"))
        st_reader.CreateIdAttr("UsdPrimvarReader_float2")
        st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")

        tex_shader = UsdShade.Shader.Define(stage, mat_prim_path.AppendChild("UVTexture"))
        tex_shader.CreateIdAttr("UsdUVTexture")
        tex_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(usd_tex_path))
        tex_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_reader.ConnectableAPI(), "result")
        tex_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        # Diffuse & Emissive (Self-illuminating for maximum visibility from camera)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex_shader.ConnectableAPI(), "rgb"
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex_shader.ConnectableAPI(), "rgb"
        )

        target_prim = stage.GetPrimAtPath(Sdf.Path(target_prim_path))
        if target_prim and target_prim.IsValid():
            UsdShade.MaterialBindingAPI(target_prim).Bind(material)
    except Exception:
        pass


def create_textured_signboard_mesh(
    stage: Usd.Stage,
    prim_path: str,
    center_pos: np.ndarray | Tuple[float, float, float],
    size_xy: Tuple[float, float],
    room_id: str,
    facing: str = "up",
) -> None:
    """
    Construct a UsdGeom.Mesh quad with explicit UV texture coordinates ('primvars:st')
    and bind the high-contrast glowing PBR material.

    Args:
        stage: The active USD stage
        prim_path: Scene prim path (e.g. /World/Hospital/Rooms/SignMesh_ICU_01)
        center_pos: Center coordinates (X, Y, Z) in meters
        size_xy: (Width, Height) in meters
        room_id: Department ID (e.g. 'ICU-01', 'EMR-01')
        facing: 'up' (horizontal overhead for isometric camera), 'north', 'south', 'east', 'west'
    """
    if not HAS_USD or UsdGeom is None or stage is None:
        return
    try:
        mesh = UsdGeom.Mesh.Define(stage, Sdf.Path(prim_path))
        cx, cy, cz = float(center_pos[0]), float(center_pos[1]), float(center_pos[2])
        w, h = float(size_xy[0]), float(size_xy[1])
        hw, hh = w / 2.0, h / 2.0

        if facing in ("up", "angled", "overhead_angled"):
            # Overhead floating label tilted 28 degrees towards South (where camera is situated)
            # This makes the signboard face directly into the isometric camera with ZERO foreshortening
            theta = np.radians(28.0)
            cos_t, sin_t = float(np.cos(theta)), float(np.sin(theta))
            y_bot = cy - hh * cos_t
            z_bot = cz - hh * sin_t
            y_top = cy + hh * cos_t
            z_top = cz + hh * sin_t
            points = [
                Gf.Vec3f(cx - hw, y_bot, z_bot),  # Bottom-Left
                Gf.Vec3f(cx + hw, y_bot, z_bot),  # Bottom-Right
                Gf.Vec3f(cx + hw, y_top, z_top),  # Top-Right
                Gf.Vec3f(cx - hw, y_top, z_top),  # Top-Left
            ]
            normals = [Gf.Vec3f(0, -sin_t, cos_t)] * 4
        elif facing == "south":
            # Vertical quad on a South doorway lintel (facing corridor at -Y)
            points = [
                Gf.Vec3f(cx - hw, cy, cz - hh),
                Gf.Vec3f(cx + hw, cy, cz - hh),
                Gf.Vec3f(cx + hw, cy, cz + hh),
                Gf.Vec3f(cx - hw, cy, cz + hh),
            ]
            normals = [Gf.Vec3f(0, -1, 0)] * 4
        elif facing == "north":
            # Vertical quad on a North doorway lintel (facing corridor at +Y)
            points = [
                Gf.Vec3f(cx + hw, cy, cz - hh),
                Gf.Vec3f(cx - hw, cy, cz - hh),
                Gf.Vec3f(cx - hw, cy, cz + hh),
                Gf.Vec3f(cx + hw, cy, cz + hh),
            ]
            normals = [Gf.Vec3f(0, 1, 0)] * 4
        elif facing == "east":
            # Vertical quad on an East doorway lintel (facing corridor at +X)
            points = [
                Gf.Vec3f(cx, cy - hw, cz - hh),
                Gf.Vec3f(cx, cy + hw, cz - hh),
                Gf.Vec3f(cx, cy + hw, cz + hh),
                Gf.Vec3f(cx, cy - hw, cz + hh),
            ]
            normals = [Gf.Vec3f(1, 0, 0)] * 4
        else:  # "west"
            # Vertical quad on a West doorway lintel (facing corridor at -X)
            points = [
                Gf.Vec3f(cx, cy + hw, cz - hh),
                Gf.Vec3f(cx, cy - hw, cz - hh),
                Gf.Vec3f(cx, cy - hw, cz + hh),
                Gf.Vec3f(cx, cy + hw, cz + hh),
            ]
            normals = [Gf.Vec3f(-1, 0, 0)] * 4

        mesh.CreatePointsAttr(points)
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateNormalsAttr(normals)
        mesh.CreateDoubleSidedAttr(True)

        # Texture Coordinates (UVs)
        # Point 0: (0.0, 0.0), Point 1: (1.0, 0.0), Point 2: (1.0, 1.0), Point 3: (0.0, 1.0)
        pv = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
        )
        pv.Set([
            Gf.Vec2f(0.0, 0.0),
            Gf.Vec2f(1.0, 0.0),
            Gf.Vec2f(1.0, 1.0),
            Gf.Vec2f(0.0, 1.0),
        ])

        # Bind signage material
        apply_signage_material(stage, prim_path, room_id)
    except Exception as e:
        print(f"[SignageGenerator] Warning: mesh creation failed for {prim_path}: {e}")
