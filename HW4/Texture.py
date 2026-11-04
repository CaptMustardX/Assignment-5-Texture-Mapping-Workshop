import sys
import math
import os
import random
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
from PIL import Image

# ตั้งค่า Working Directory ให้ตรงกับตำแหน่งไฟล์ Texture.py
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except Exception:
    pass

# ==========================================
# 0. PURE PYTHON MATRIX HELPERS (NO NUMPY)
# ==========================================
def mat3_mul_vec3(m, v):
    return [
        m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2],
        m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2],
        m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2]
    ]

def mat3_mul_mat3(a, b):
    res = [[0.0]*3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            res[i][j] = sum(a[i][k] * b[k][j] for k in range(3))
    return res

# ==========================================
# 1. TEXTURE CONVERTER
# ==========================================
def pil_to_gl_texture(img):
    img_flipped = img.transpose(Image.FLIP_TOP_BOTTOM)
    img_data = img_flipped.convert("RGBA").tobytes()
    w, h = img_flipped.size
    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
    return tex_id

# ==========================================
# 2. 3D GEOMETRY DRAWING & ANIMATED RUBRIC
# ==========================================
def draw_textured_sphere(radius=1.8, lats=40, lons=40):
    for i in range(lats):
        lat0 = math.pi * (-0.5 + float(i) / lats)
        z0 = radius * math.sin(lat0)
        zr0 = radius * math.cos(lat0)
        v0 = float(i) / lats

        lat1 = math.pi * (-0.5 + float(i + 1) / lats)
        z1 = radius * math.sin(lat1)
        zr1 = radius * math.cos(lat1)
        v1 = float(i + 1) / lats

        glBegin(GL_QUAD_STRIP)
        for j in range(lons + 1):
            lng = 2 * math.pi * float(j) / lons
            x = math.cos(lng)
            y = math.sin(lng)
            u = float(j) / lons

            glNormal3f(x * zr0 / radius, y * zr0 / radius, z0 / radius)
            glTexCoord2f(u, v0)
            glVertex3f(x * zr0, y * zr0, z0)

            glNormal3f(x * zr1 / radius, y * zr1 / radius, z1 / radius)
            glTexCoord2f(u, v1)
            glVertex3f(x * zr1, y * zr1, z1)
        glEnd()

def draw_cube_with_6_textures(textures, size=1.3):
    s = size
    faces = [
        (0, [(-s,-s, s), ( s,-s, s), ( s, s, s), (-s, s, s)], (0, 0, 1)),
        (1, [( s,-s,-s), (-s,-s,-s), (-s, s,-s), ( s, s,-s)], (0, 0,-1)),
        (2, [(-s, s, s), ( s, s, s), ( s, s,-s), (-s, s,-s)], (0, 1, 0)),
        (3, [(-s,-s,-s), ( s,-s,-s), ( s,-s, s), (-s,-s, s)], (0,-1, 0)),
        (4, [( s,-s, s), ( s,-s,-s), ( s, s,-s), ( s, s, s)], (1, 0, 0)),
        (5, [(-s,-s,-s), (-s,-s, s), (-s, s, s), (-s, s,-s)], (-1, 0, 0))
    ]

    for tex_idx, verts, norm in faces:
        glBindTexture(GL_TEXTURE_2D, textures[tex_idx])
        glBegin(GL_QUADS)
        glNormal3f(*norm)
        glTexCoord2f(0.0, 0.0); glVertex3f(*verts[0])
        glTexCoord2f(1.0, 0.0); glVertex3f(*verts[1])
        glTexCoord2f(1.0, 1.0); glVertex3f(*verts[2])
        glTexCoord2f(0.0, 1.0); glVertex3f(*verts[3])
        glEnd()

class RubiksCube:
    def __init__(self, textures):
        self.textures = textures
        self.cubies = []
        for x in [-1, 0, 1]:
            for y in [-1, 0, 1]:
                for z in [-1, 0, 1]:
                    self.cubies.append({
                        'pos': [float(x), float(y), float(z)],
                        'orig': (x, y, z),
                        'rot': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
                    })
        
        # ระบบแอนิเมชันและคิวการหมุน
        self.is_animating = False
        self.anim_axis = 'X'
        self.anim_layer = 0
        self.anim_angle = 0.0
        self.anim_target_angle = 90.0
        self.anim_speed = 15.0  # ความเร็วหมุนองศาต่อเฟรม
        self.current_record_history = True

        # ประวัติการหมุน & คิวแอนิเมชันสำหรับ Auto Solve / Scramble
        self.history = []        # [(axis, layer, angle), ...]
        self.action_queue = []   # [(axis, layer, angle, record_history), ...]

    def rotate_layer(self, axis, layer_val, angle_deg=90, record_history=True):
        if self.is_animating or len(self.action_queue) > 0:
            self.action_queue.append((axis, layer_val, angle_deg, record_history))
        else:
            self._start_animation(axis, layer_val, angle_deg, record_history)

    def _start_animation(self, axis, layer_val, angle_deg, record_history):
        self.is_animating = True
        self.anim_axis = axis
        self.anim_layer = layer_val
        self.anim_target_angle = float(angle_deg)
        self.anim_angle = 0.0
        self.current_record_history = record_history

    def scramble(self, num_moves=10):
        """ระบบสุ่มหมุนลูก Rubric"""
        valid_moves = [
            ('Z', 1, 90), ('Z', -1, 90),
            ('X', -1, 90), ('X', 1, 90),
            ('Y', 1, 90), ('Y', -1, 90)
        ]
        for _ in range(num_moves):
            move = random.choice(valid_moves)
            self.rotate_layer(move[0], move[1], move[2], record_history=True)

    def auto_solve(self):
        """ระบบย้อนประวัติการหมุนเพื่อแก้กลับเป็นสภาพเดิม"""
        while self.history:
            axis, layer_val, angle = self.history.pop()
            self.action_queue.append((axis, layer_val, -angle, False))

    def update_animation(self):
        if not self.is_animating:
            if self.action_queue:
                next_move = self.action_queue.pop(0)
                self._start_animation(next_move[0], next_move[1], next_move[2], next_move[3])
            return

        step = self.anim_speed if self.anim_target_angle > 0 else -self.anim_speed
        self.anim_angle += step

        if abs(self.anim_angle) >= abs(self.anim_target_angle):
            self._apply_final_rotation(self.anim_axis, self.anim_layer, self.anim_target_angle)
            if self.current_record_history:
                self.history.append((self.anim_axis, self.anim_layer, self.anim_target_angle))
            
            self.is_animating = False
            self.anim_angle = 0.0
            
            if self.action_queue:
                next_move = self.action_queue.pop(0)
                self._start_animation(next_move[0], next_move[1], next_move[2], next_move[3])

    def _apply_final_rotation(self, axis, layer_val, angle_deg):
        rad = math.radians(angle_deg)
        c_val, s_val = math.cos(rad), math.sin(rad)
        
        if axis == 'X':
            r_mat = [[1.0, 0.0, 0.0], [0.0, c_val, -s_val], [0.0, s_val, c_val]]
            idx = 0
        elif axis == 'Y':
            r_mat = [[c_val, 0.0, s_val], [0.0, 1.0, 0.0], [-s_val, 0.0, c_val]]
            idx = 1
        else:
            r_mat = [[c_val, -s_val, 0.0], [s_val, c_val, 0.0], [0.0, 0.0, 1.0]]
            idx = 2

        for cb in self.cubies:
            if abs(cb['pos'][idx] - layer_val) < 0.1:
                new_pos = mat3_mul_vec3(r_mat, cb['pos'])
                cb['pos'] = [round(new_pos[0]), round(new_pos[1]), round(new_pos[2])]
                cb['rot'] = mat3_mul_mat3(r_mat, cb['rot'])

    def draw(self):
        self.update_animation()
        
        sz = 0.45
        gap = 0.96
        axis_idx = ['X', 'Y', 'Z'].index(self.anim_axis) if self.is_animating else 0

        for c in self.cubies:
            glPushMatrix()

            in_anim_layer = self.is_animating and (abs(c['pos'][axis_idx] - self.anim_layer) < 0.1)
            if in_anim_layer:
                if self.anim_axis == 'X':
                    glRotatef(self.anim_angle, 1, 0, 0)
                elif self.anim_axis == 'Y':
                    glRotatef(self.anim_angle, 0, 1, 0)
                elif self.anim_axis == 'Z':
                    glRotatef(self.anim_angle, 0, 0, 1)

            px, py, pz = c['pos'][0] * gap, c['pos'][1] * gap, c['pos'][2] * gap
            glTranslatef(px, py, pz)

            r = c['rot']
            gl_mat = [
                r[0][0], r[1][0], r[2][0], 0.0,
                r[0][1], r[1][1], r[2][1], 0.0,
                r[0][2], r[1][2], r[2][2], 0.0,
                0.0,     0.0,     0.0,     1.0
            ]
            glMultMatrixf(gl_mat)

            ox, oy, oz = c['orig']

            faces = [
                (0, [(-sz,-sz, sz), ( sz,-sz, sz), ( sz, sz, sz), (-sz, sz, sz)], (0,0,1), ox, oy, oz==1),
                (1, [( sz,-sz,-sz), (-sz,-sz,-sz), (-sz, sz,-sz), ( sz, sz,-sz)], (0,0,-1), -ox, oy, oz==-1),
                (2, [(-sz, sz, sz), ( sz, sz, sz), ( sz, sz,-sz), (-sz, sz,-sz)], (0,1,0), ox, -oz, oy==1),
                (3, [(-sz,-sz,-sz), ( sz,-sz,-sz), ( sz,-sz, sz), (-sz,-sz, sz)], (0,-1,0), ox, oz, oy==-1),
                (4, [( sz,-sz, sz), ( sz,-sz,-sz), ( sz, sz,-sz), ( sz, sz, sz)], (1,0,0), -oz, oy, ox==1),
                (5, [(-sz,-sz,-sz), (-sz,-sz, sz), (-sz, sz, sz), (-sz, sz,-sz)], (-1,0,0), oz, oy, ox==-1)
            ]

            for tex_idx, verts, norm, tile_x, tile_y, is_outer in faces:
                if is_outer:
                    glBindTexture(GL_TEXTURE_2D, self.textures[tex_idx])
                    u0 = (tile_x + 1) / 3.0
                    u1 = (tile_x + 2) / 3.0
                    v0 = (tile_y + 1) / 3.0
                    v1 = (tile_y + 2) / 3.0
                else:
                    glBindTexture(GL_TEXTURE_2D, 0)
                    u0, u1, v0, v1 = 0, 0, 0, 0

                glBegin(GL_QUADS)
                glNormal3f(*norm)
                glTexCoord2f(u0, v0); glVertex3f(*verts[0])
                glTexCoord2f(u1, v0); glVertex3f(*verts[1])
                glTexCoord2f(u1, v1); glVertex3f(*verts[2])
                glTexCoord2f(u0, v1); glVertex3f(*verts[3])
                glEnd()

            glPopMatrix()

# ==========================================
# 3. GUI ENGINE & MAIN APPLICATION
# ==========================================
class App:
    def __init__(self):
        pygame.init()
        self.width, self.height = 1280, 720
        pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("3D Texture Mapping Studio - OpenPyGL")

        self.mode = 1
        self.rot_x = 20.0
        self.rot_y = -30.0
        self.zoom = -6.0
        self.auto_rotate = True
        self.is_dragging = False
        self.last_mouse = (0, 0)

        glEnable(GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        self.init_textures()
        self.rubik = RubiksCube(self.cube_textures)

    def init_textures(self):
        # -------------------------------------------------------------
        # 1. รูปภาพสำหรับ Sphere (โหมด 1: Sphere)
        # -------------------------------------------------------------
        img_single = Image.open("Milky.jpg")
        self.single_tex = pil_to_gl_texture(img_single)

        # -------------------------------------------------------------
        # 2. รูปภาพ 6 ภาพสำหรับ Cube และ Rubik (โหมด 2 และ 4)
        # -------------------------------------------------------------
        image_files = [
            "Rick.png",     # ด้าน 1: หน้า (FRONT)
            "American.jpg", # ด้าน 2: หลัง (BACK)
            "Crazy.png",    # ด้าน 3: บน (TOP)
            "Spider.jpg",   # ด้าน 4: ล่าง (BOTTOM)
            "Spooky.jpg",   # ด้าน 5: ขวา (RIGHT)
            "Man.png"       # ด้าน 6: ซ้าย (LEFT)
        ]
        self.cube_textures = []
        for file_path in image_files:
            img = Image.open(file_path)
            self.cube_textures.append(pil_to_gl_texture(img))

        # -------------------------------------------------------------
        # 3. รูปภาพแผนที่โลกสำหรับ Earth Sphere (โหมด 3: Planet Earth)
        # -------------------------------------------------------------
        img_earth = Image.open("Earth.jpg")
        self.earth_tex = pil_to_gl_texture(img_earth)

    def render_ui(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, self.width, self.height, 0)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)

        ui_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
        pygame.draw.rect(ui_surface, (20, 24, 33, 220), (20, 20, 280, 680), border_radius=16)
        pygame.draw.rect(ui_surface, (60, 70, 90, 150), (20, 20, 280, 680), width=2, border_radius=16)

        font_title = pygame.font.SysFont("Segoe UI", 20, bold=True)
        font_sub = pygame.font.SysFont("Segoe UI", 13)
        font_btn = pygame.font.SysFont("Segoe UI", 15, bold=True)

        title_txt = font_title.render("TEXTURE MAPPER", True, (240, 245, 255))
        sub_txt = font_sub.render("Python OpenGL Studio", True, (120, 140, 170))
        ui_surface.blit(title_txt, (40, 40))
        ui_surface.blit(sub_txt, (40, 68))

        modes = [
            (1, "1. Sphere"),
            (2, "2. Cube"),
            (3, "3. Planet Earth"),
            (4, "4. Interactive Rubric")
        ]

        self.buttons = []
        for idx, (m_id, label) in enumerate(modes):
            bx, by, bw, bh = 40, 110 + idx * 55, 240, 44
            is_active = (self.mode == m_id)
            
            bg_col = (50, 110, 230) if is_active else (35, 42, 56)
            text_col = (255, 255, 255) if is_active else (170, 185, 205)
            
            pygame.draw.rect(ui_surface, bg_col, (bx, by, bw, bh), border_radius=8)
            if is_active:
                pygame.draw.rect(ui_surface, (100, 170, 255), (bx, by, bw, bh), width=2, border_radius=8)
                
            txt = font_btn.render(label, True, text_col)
            ui_surface.blit(txt, (bx + 15, by + 12))
            self.buttons.append((m_id, pygame.Rect(bx, by, bw, bh)))

        # แผงคู่มือการควบคุม
        pygame.draw.rect(ui_surface, (30, 36, 48, 180), (40, 335, 240, 160), border_radius=10)
        guide_lines = [
            "CONTROLS",
            "• Left Drag: Orbit Rotate",
            "• Scroll Wheel: Zoom In/Out",
            "• Spacebar: Toggle Auto-360",
            "• Rubric Layer Rotation:",
            "  [W] [A] [S] [D] [Q] [E]"
        ]
        for i, line in enumerate(guide_lines):
            col = (100, 200, 255) if i == 0 else (180, 195, 215)
            f = font_sub if i > 0 else font_btn
            txt = f.render(line, True, col)
            ui_surface.blit(txt, (52, 345 + i * 24))

        # แสดงปุ่ม Scramble & Auto Solve เฉพาะตอนเลือกโหมด 4 (Interactive Rubric)
        if self.mode == 4:
            # ปุ่ม Scramble
            pygame.draw.rect(ui_surface, (180, 100, 30), (40, 510, 115, 38), border_radius=8)
            scr_txt = font_btn.render("Scramble", True, (255, 255, 255))
            ui_surface.blit(scr_txt, (62, 520))
            self.buttons.append(('scramble', pygame.Rect(40, 510, 115, 38)))

            # ปุ่ม Auto Solve
            pygame.draw.rect(ui_surface, (120, 60, 180), (165, 510, 115, 38), border_radius=8)
            sol_txt = font_btn.render("Auto Solve", True, (255, 255, 255))
            ui_surface.blit(sol_txt, (180, 520))
            self.buttons.append(('solve', pygame.Rect(165, 510, 115, 38)))

            # ปุ่ม Toggle Auto-Rotate (ตำแหน่งล่างสุด)
            auto_col = (40, 160, 90) if self.auto_rotate else (140, 50, 50)
            pygame.draw.rect(ui_surface, auto_col, (40, 560, 240, 38), border_radius=8)
            auto_txt = font_btn.render(f"Auto-Rotate: {'ON' if self.auto_rotate else 'OFF'}", True, (255, 255, 255))
            ui_surface.blit(auto_txt, (70, 570))
            self.buttons.append(('auto', pygame.Rect(40, 560, 240, 38)))
        else:
            # โหมด 1-3 ปุ่ม Auto-Rotate ปรากฏปกติ
            auto_col = (40, 160, 90) if self.auto_rotate else (140, 50, 50)
            pygame.draw.rect(ui_surface, auto_col, (40, 510, 240, 40), border_radius=8)
            auto_txt = font_btn.render(f"Auto-Rotate: {'ON' if self.auto_rotate else 'OFF'}", True, (255, 255, 255))
            ui_surface.blit(auto_txt, (70, 520))
            self.buttons.append(('auto', pygame.Rect(40, 510, 240, 40)))

        # แถบแสดงสถานะด้านล่าง
        pygame.draw.rect(ui_surface, (20, 24, 33, 200), (320, 650, 940, 50), border_radius=12)
        status_str = f"Current Mode: Mode {self.mode}  |  Rotation X: {int(self.rot_x)}° Y: {int(self.rot_y)}°  |  Zoom: {abs(round(self.zoom,1))}"
        st_txt = font_sub.render(status_str, True, (180, 200, 230))
        ui_surface.blit(st_txt, (340, 666))

        try:
            ui_data = pygame.image.tostring(ui_surface, "RGBA", False)
        except AttributeError:
            ui_data = pygame.image.tobytes(ui_surface, "RGBA", False)

        glEnable(GL_TEXTURE_2D)
        ui_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, ui_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width, self.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, ui_data)

        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(self.width, 0)
        glTexCoord2f(1, 1); glVertex2f(self.width, self.height)
        glTexCoord2f(0, 1); glVertex2f(0, self.height)
        glEnd()

        glDeleteTextures([ui_tex])

        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def run(self):
        clock = pygame.time.Clock()
        
        while True:
            dt = clock.tick(60)
            
            if self.auto_rotate:
                self.rot_y += 0.6

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()

                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mx, my = event.pos
                        clicked_btn = False
                        for b_id, rect in self.buttons:
                            if rect.collidepoint(mx, my):
                                if b_id == 'auto':
                                    self.auto_rotate = not self.auto_rotate
                                elif b_id == 'scramble':
                                    self.rubik.scramble(10)
                                elif b_id == 'solve':
                                    self.rubik.auto_solve()
                                else:
                                    self.mode = b_id
                                clicked_btn = True
                                break
                        if not clicked_btn:
                            self.is_dragging = True
                            self.last_mouse = event.pos

                    elif event.button == 4:
                        self.zoom = min(self.zoom + 0.4, -2.5)
                    elif event.button == 5:
                        self.zoom = max(self.zoom - 0.4, -15.0)

                elif event.type == MOUSEBUTTONUP:
                    if event.button == 1:
                        self.is_dragging = False

                elif event.type == MOUSEMOTION:
                    if self.is_dragging:
                        dx = event.pos[0] - self.last_mouse[0]
                        dy = event.pos[1] - self.last_mouse[1]
                        self.rot_y += dx * 0.5
                        self.rot_x += dy * 0.5
                        self.last_mouse = event.pos

                elif event.type == KEYDOWN:
                    if event.key == K_SPACE:
                        self.auto_rotate = not self.auto_rotate
                    elif self.mode == 4:
                        if event.key == K_w: self.rubik.rotate_layer('Z', 1, 90)
                        elif event.key == K_a: self.rubik.rotate_layer('Z', -1, 90)
                        elif event.key == K_s: self.rubik.rotate_layer('X', -1, 90)
                        elif event.key == K_d: self.rubik.rotate_layer('X', 1, 90)
                        elif event.key == K_q: self.rubik.rotate_layer('Y', 1, 90)
                        elif event.key == K_e: self.rubik.rotate_layer('Y', -1, 90)

            glClearColor(0.06, 0.08, 0.12, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45, (self.width / self.height), 0.1, 100.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glTranslatef(0.8, 0.0, self.zoom)
            glRotatef(self.rot_x, 1, 0, 0)
            glRotatef(self.rot_y, 0, 1, 0)

            if self.mode == 1:
                glBindTexture(GL_TEXTURE_2D, self.single_tex)
                draw_textured_sphere()
            elif self.mode == 2:
                draw_cube_with_6_textures(self.cube_textures)
            elif self.mode == 3:
                glBindTexture(GL_TEXTURE_2D, self.earth_tex)
                draw_textured_sphere()
            elif self.mode == 4:
                self.rubik.draw()

            self.render_ui()
            pygame.display.flip()

if __name__ == "__main__":
    app = App()
    app.run()