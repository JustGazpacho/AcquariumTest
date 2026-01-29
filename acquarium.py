import json
import random
import time
import math
import sys
import os

school_directions = {}
CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def move(y, x):
    return f"\033[{y};{x}H"

def fg(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"

def bg(r, g, b):
    return f"\033[48;2;{r};{g};{b}m"

RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR = "\033[2J"

WINDOWS = os.name == "nt"

if WINDOWS:
    import msvcrt
else:
    import termios
    import tty
    import select

def key_pressed():
    if WINDOWS:
        return msvcrt.kbhit()
    else:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        return dr != []

def get_key():
    if WINDOWS:
        return msvcrt.getch().decode(errors="ignore")
    else:
        return sys.stdin.read(1)

def enable_raw_mode():
    if not WINDOWS:
        global old_settings
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)

def disable_raw_mode():
    if not WINDOWS:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


class Renderer:
    def __init__(self, height, width):
        self.h = height
        self.w = width
        
        self.front = [[None for _ in range(self.w)] for _ in range(self.h)]
        self.back  = [[None for _ in range(self.w)] for _ in range(self.h)]

    def clear_back(self):
        for y in range(self.h):
            for x in range(self.w):
                self.back[y][x] = None

    def set_cell(self, y, x, ch, fg_code="", bg_code=""):
        if 0 <= y < self.h and 0 <= x < self.w:
            self.back[y][x] = (ch, fg_code, bg_code)

    def blit_static_layer(self, static_layer):
        
        for y in range(self.h):
            row_s = static_layer[y]
            row_b = self.back[y]
            for x in range(self.w):
                row_b[x] = row_s[x]

    def flush(self, force=False):
        out = []
        for y in range(self.h):
            for x in range(self.w):
                new_cell = self.back[y][x]
                if new_cell is None:
                    
                    new_cell = (" ", "", "")
                    self.back[y][x] = new_cell

                old_cell = self.front[y][x]

                if force or new_cell != old_cell:
                    self.front[y][x] = new_cell
                    ch, fg_code, bg_code = new_cell
                    out.append(
                        move(y + 1, x + 1) + RESET + fg_code + bg_code + ch + RESET
                    )

        if out:
            sys.stdout.write("".join(out))
            sys.stdout.flush()

class StaticObject:
    def __init__(self, y, x, shape, rgb_fg=None, rgb_bg=None):
        self.y = y
        self.x = x
        self.shape = shape
        self.rgb_fg = rgb_fg
        self.rgb_bg = rgb_bg    

    def draw_on_layer(self, layer):
        for dy, line in enumerate(self.shape):
            for dx, ch in enumerate(line):
                if ch != " ":
                    yy = self.y + dy
                    xx = self.x + dx
                    if 0 <= yy < len(layer) and 0 <= xx < len(layer[0]):
                        fg_code = fg(*self.rgb_fg) if self.rgb_fg else ""
                        bg_code = bg(*self.rgb_bg) if self.rgb_bg else ""
                        layer[yy][xx] = (ch, fg_code, bg_code)


class Bubble:
    def __init__(self, max_y, max_x, visible_y, rgb_fg=None, rgb_bg=None):
        self.rgb_fg = rgb_fg
        self.rgb_bg = rgb_bg
        self.max_y = max_y
        self.max_x = max_x
        self.visible_y = visible_y
        self.reset()

    def reset(self):
        self.y = random.randint(self.max_y - 3, self.max_y - 2)
        self.x = random.randint(2, self.max_x - 3)
        self.char = random.choice(["o", "O", "0", "."])
        self.vy = -random.uniform(0.05, 0.12)
        self.vx = random.uniform(-0.03, 0.03)

    def update(self, dt):
        self.y += self.vy * dt * 60
        self.x += self.vx * dt * 60

        self.vx += random.uniform(-0.005, 0.005)
        self.vx = max(min(self.vx, 0.08), -0.08)

        if self.y < 0 or self.x < 0 or self.x > self.max_x - 1:
            self.reset()

    def draw(self, renderer):
        iy = int(self.y)
        ix = int(self.x)
        fg_code = fg(*self.rgb_fg) if self.rgb_fg else ""
        bg_code = bg(*self.rgb_bg) if self.rgb_bg else ""
        
        if 0 <= iy < renderer.h and 0 <= ix < renderer.w:
            renderer.set_cell(iy, ix, self.char, fg_code, bg_code)


FLIP_MAP = str.maketrans("()[]{}<>/\\", ")(][}{><\\/")

def flip_line(line):
    return line[::-1].translate(FLIP_MAP)

def assign_school(fish, fish_list):
    cfg = fish.school_cfg
    max_size = cfg.get("max_school_size")
    max_schools = cfg.get("max_schools")

    if not max_size or not max_schools:
        return None

    schools = {}
    for f in fish_list:
        if f.name == fish.name and f.school_id is not None:
            schools.setdefault(f.school_id, 0)
            schools[f.school_id] += 1

    for sid, count in schools.items():
        if count < max_size:
            return sid

    if len(schools) < max_schools:
        return max(schools.keys(), default=-1) + 1

    return random.choice(list(schools.keys()))


class Fish:
    def __init__(self, max_y, max_x, cfg, visible_y):
        self.max_y = max_y
        self.max_x = max_x
        self.visible_y = visible_y
        self.cfg = cfg
        self.school_cfg = self.cfg.get("schooling", {})
        self.school_id = None
        self.reset()

    def reset(self):
        self.name = self.cfg["name"]


        self.frames = self.cfg.get("shape_frames")
        self.animation_speed = self.cfg.get("animation_speed", 0.3)
        self.anim_time = 0.0
        self.anim_index = 0

        if self.frames:
            self.base_frames = [list(frame) for frame in self.frames]
            self.shape = self.base_frames[0]
        else:
            raw_shape = self.cfg["shape"]
            if isinstance(raw_shape[0], list):
                self.base_frames = [[row for row in raw_shape[0]]]
            else:
                self.base_frames = [raw_shape]
            self.shape = self.base_frames[0]

        self.rgb_fg = self.cfg.get("rgb_fg")
        self.rgb_bg = self.cfg.get("rgb_bg")

        self.speed = self.cfg["speed"]
        self.role = self.cfg.get("role", "prey")
        self.max_population = self.cfg.get("max_population", 999)
        self.preferred_depth = self.cfg.get("preferred_depth")
        self.vertical_bias = self.cfg.get("vertical_bias", 0.0)
        self.flip_allowed = self.cfg.get("flip_allowed", True)

        self.height = len(self.shape)
        self.width = max(len(row) for row in self.shape)

        if self.preferred_depth == "bottom":
            base_y = self.visible_y - self.height - 1
            self.y = base_y + random.uniform(-1, 1)
        else:
            self.y = random.randint(1, max(1, self.visible_y - self.height - 2))

        self.x = random.randint(0, max(0, self.max_x - self.width - 1))
        self.direction = random.choice(["left", "right"])
        self.intent_dir = self.direction
        self.dead = False

        self.age = 0.0
        self.breed_cooldown = random.uniform(5.0, 15.0)

        if self.direction == "left" and self.flip_allowed:
            self._flip_all_frames()


    def _flip_all_frames(self):
        def flip_frame(frame):
            return [flip_line(row) for row in frame]
        self.base_frames = [flip_frame(frame) for frame in self.base_frames]
        self.shape = self.base_frames[self.anim_index]

    def _flip_direction(self):
        if not self.flip_allowed:
            self.direction = "right" if self.direction == "left" else "left"
            return
        self.direction = "right" if self.direction == "left" else "left"
        self._flip_all_frames()

    def animate(self, dt):
        if not self.base_frames or len(self.base_frames) <= 1:
            return
        self.anim_time += dt
        if self.anim_time >= self.animation_speed:
            self.anim_time = 0.0
            self.anim_index = (self.anim_index + 1) % len(self.base_frames)
            self.shape = self.base_frames[self.anim_index]

    def schooling(self, fish_list):
        if self.preferred_depth == "bottom" or self.name == "jelly":
            return

        NEIGHBOR_RADIUS_X = 35
        NEIGHBOR_RADIUS_Y = 8
        COHESION_FACTOR   = 0.02
        ALIGN_FACTOR      = 0.15
        SEPARATION_DIST   = 1.2
        SEPARATION_FORCE  = 0.25
        JITTER_AMOUNT     = 0.03
        WAVE_STRENGTH     = 0.15
        WAVE_SPEED        = 0.8
        cfg = self.school_cfg

        NEIGHBOR_RADIUS_X = cfg.get("neighbor_radius_x", 35)
        NEIGHBOR_RADIUS_Y = cfg.get("neighbor_radius_y", 8)
        ALIGN_CHANCE = cfg.get("alignment_chance", 0.15)
        COHESION = cfg.get("cohesion", 0.02)
        JITTER_AMOUNT = cfg.get("jitter", 0.03)
        WAVE_STRENGTH = cfg.get("wave_strength", 0.15)
        LANE_LOCK = cfg.get("lane_lock", True)

        neighbors = [
            f for f in fish_list
            if f is not self
            and not f.dead
            and f.name == self.name
            and f.school_id == self.school_id
            and abs(f.x - self.x) < NEIGHBOR_RADIUS_X
            and abs(f.y - self.y) < NEIGHBOR_RADIUS_Y
        ]

        if not neighbors:
            self.y += random.uniform(-0.05, 0.05)
            return

        leader = max(neighbors, key=lambda f: f.age)

        avg_y = sum(f.y for f in neighbors) / len(neighbors)
        self.y += (avg_y - self.y) * 0.002
        spread = random.uniform(-0.3, 0.3)
        self.y += spread * 0.02

        right_count = sum(1 for f in neighbors if f.direction == "right")
        new_dir = "right" if right_count > len(neighbors) / 2 else "left"

        if random.random() < ALIGN_CHANCE:
            self.intent_dir = new_dir

        MIN_DX = cfg.get("min_dx", 5.0)
        SEP_X  = cfg.get("sep_force_x", 0.15)

        MIN_DY = cfg.get("min_dy", 2.0)
        SEP_Y  = cfg.get("sep_force_y", 0.05)

        for f in neighbors:
            dx = self.x - f.x
            dy = self.y - f.y

            adx = abs(dx)
            ady = abs(dy)

          
            if adx < MIN_DX and adx > 0:
                push = (MIN_DX - adx) / MIN_DX
                self.x += (1 if dx > 0 else -1) * push * SEP_X

            
            if ady < MIN_DY and ady > 0:
                push = (MIN_DY - ady) / MIN_DY
                self.y += (1 if dy > 0 else -1) * push * SEP_Y


        if LANE_LOCK:
            lane_height = 2.2
            target_lane = round(self.y / lane_height) * lane_height
            self.y += (target_lane - self.y) * 0.015

       
        predators = [
            f for f in neighbors
            if f.role == "predator"
        ]
        if predators:
            self.intent_dir = "right" if self.direction == "left" else "left"


        
        self.y += math.sin(time.time() * WAVE_SPEED + self.x * 0.1) * WAVE_STRENGTH 

        
        self.y += random.uniform(-JITTER_AMOUNT, JITTER_AMOUNT)
        MID = self.visible_y * 0.45
        self.y += (MID - self.y) * 0.005

        
        self.y = max(1, min(self.y, self.visible_y - self.height - 2))

    def jellyfish_movement(self, dt, border_behavior="wrap"):
        wander = self.cfg.get("vertical_wander", 0.05)
        self.y += math.sin(time.time() * 1.2 + self.x * 0.1) * 0.03
        self.y += random.uniform(-wander, wander)

        if random.random() < self.cfg.get("propulsion_chance", 0.02):
            self.y -= random.uniform(0.8, 1.5)

        self.x += math.sin(time.time() * 0.8 + self.y * 0.2) * 0.05

        if border_behavior == "wrap":
            if self.y > self.visible_y - self.height - 5:
                self.y -= 0.5

            upper_limit = 2.5
            if self.y < upper_limit:
                
                push = (upper_limit - self.y) * 0.3
                self.y += push

            
            self.x %= max(1, self.max_x - self.width)

        elif border_behavior == "bounce":
            
            if not hasattr(self, "_vx"):
                self._vx = 0.05
                self._vy = 0.02

            self.x += self._vx
            self.y += self._vy

            
            if self.x < 0:
                self.x = 0
                self._vx = abs(self._vx)
            elif self.x > self.max_x - self.width:
                self.x = self.max_x - self.width
                self._vx = -abs(self._vx)

            
            if self.y < 2:  
                self.y = 2
                self._vy = abs(self._vy)  
            elif self.y > self.visible_y - self.height:
                self.y = self.visible_y - self.height
                self._vy = -abs(self._vy)

    def update(self, dt, fish_list):
        self.age += dt
        self.breed_cooldown -= dt

        if self.age > 80 and random.random() < 0.0005 * dt * 60:
             
            return

        self.animate(dt)

        if self.name == "jelly":
            self.jellyfish_movement(dt)
        else:
            self.schooling(fish_list)

        
        if self.school_id in school_directions:
            bank_dir = school_directions[self.school_id]
            self.intent_dir = "right" if bank_dir > 0 else "left"

        
        dx = self.speed * dt * 35 

        if self.direction == "right":
            self.x += dx
        else:
            self.x -= dx


        if self.direction == "right" and self.x >= self.max_x - 1:
            self.x = -self.width

        elif self.direction == "left" and self.x <= -self.width + 1:
            self.x = self.max_x

        if self.preferred_depth == "bottom":
            self.y = self.visible_y - self.height - 1

    def can_breed(self, current_population):
        if self.breed_cooldown > 0:
            return False
        if current_population >= self.max_population:
            return False
        return random.random() < 0.02

    def erase(self, renderer, static_layer):
        for dy in range(self.height):
            for dx in range(self.shape):
                px = int(self.x) + dx
                py = int(self.y) + dy
                if 0 <= px < renderer.w and 0 <= py < renderer.h:
                    ch, fg_code, bg_code = static_layer[py][px]
                    renderer.set_cell(py, px, ch, fg_code, bg_code)


    def draw(self, renderer):
        if self.dead:
            px = int(self.x) + dx
            py = int(self.y) + dy
            if 0 <= px < renderer.w and 0 <= py < renderer.h:
                renderer.set_cell(py, px, " ", "", "")
            return

        fg_code = fg(*self.rgb_fg) if self.rgb_fg else ""
        bg_code = bg(*self.rgb_bg) if self.rgb_bg else ""

        for dy, line in enumerate(self.shape):
            for dx, ch in enumerate(line):
                if ch == " ":
                    continue
                px = int(self.x) + dx
                py = int(self.y) + dy
                if 0 <= px < renderer.w and 0 <= py < renderer.h:
                    renderer.set_cell(py, px, ch, fg_code, bg_code)


def find_free_x_position(width, visible_x, occupied):
    if not occupied:
        max_x = visible_x - width
        return random.randint(0, max_x) if max_x >= 0 else 0

    free_spaces = []

    first_start = occupied[0][0]
    if first_start >= width:
        free_spaces.append((0, first_start))

    for (s1, e1), (s2, e2) in zip(occupied, occupied[1:]):
        gap = s2 - e1
        if gap >= width:
            free_spaces.append((e1, s2))

    last_end = occupied[-1][1]
    if visible_x - last_end >= width:
        free_spaces.append((last_end, visible_x))

    if not free_spaces:
        return random.randint(0, max(0, visible_x - width))

    start, end = random.choice(free_spaces)
    max_x = end - width
    return random.randint(start, max_x)
 

def bubble_intro(renderer, static_layer, visible_y, visible_x,timesleep=0.05):
    bubbles = []
    for x in range(visible_x):
        bubbles.append({
            "x": x,
            "y": visible_y + random.randint(0, 3),
            "char": random.choice(["o", "O", ".", "0"])
        })

    steps = visible_y + 3

    for step in range(steps):
        renderer.clear_back()
        renderer.blit_static_layer(static_layer)

        for b in bubbles:
            yy = b["y"] - step
            if 0 <= yy < visible_y:
                renderer.set_cell(yy, b["x"], b["char"])

        renderer.flush(force=False)
        time.sleep(timesleep)


def sweep_bottom(renderer, static_layer, visible_y, visible_x):
    for y in range(visible_y - 2, visible_y):  
        for x in range(visible_x):
            ch, fg_code, bg_code = static_layer[y][x]
            if ch in [" ", "_", "_-", ":-", "-", "~", "^", "`"]:
                # Simula update della cella
                renderer.front[y][x] = ("","","")
                renderer.set_cell(y, x, ch, fg_code, bg_code)
                



def main():
    config = load_config()
    enable_raw_mode()

    try:
        size = os.get_terminal_size()
        visible_x = size.columns
        visible_y = size.lines
    except:
        visible_x = 120
        visible_y = 40

    world_y = visible_y
    world_x = visible_x

    renderer = Renderer(visible_y, visible_x)

    # --- COSTRUZIONE STATIC_LAYER ---
    static_layer = [[(" ", "", "") for _ in range(visible_x)] for _ in range(visible_y)]
    static_objects = []
    occupied = []

    # 1) Posizionamento oggetti statici come prima
    for obj in config["static_objects"]:
        shape = obj["shape"]
        h = len(shape)
        w = max(len(line) for line in shape)
        count = obj.get("count", 1)

        for _ in range(count):
            y = visible_y - obj["y_offset_from_bottom"] - h
            if y < 0:
                y = 0

            if obj.get("random_x", False):
                x = find_free_x_position(w, visible_x, occupied)
            else:
                x = obj.get("x", 0)
                if x + w > visible_x:
                    x = max(0, visible_x - w)

            occupied.append((x, x + w))
            occupied.sort()

            so = StaticObject(
                y, x, shape,
                rgb_fg=obj.get("rgb_fg"),
                rgb_bg=obj.get("rgb_bg")
            )
            static_objects.append(so)
            so.draw_on_layer(static_layer)

    # 2) Riempimento sabbia negli spazi liberi
    rgb_sand = config.get("rgb_sand", [194, 178, 128])
    sand_chars = [",", ".", ":", "_", "-", "`", "~"]

    for y in range(max(0, visible_y - 2), visible_y):
        for x in range(visible_x):
            # Disegni la sabbia solo se la cella è vuota
            if static_layer[y][x] == ("", "", "") or static_layer[y][x][0] == " ":
                ch = random.choice(sand_chars)
                fg_code = fg(*rgb_sand)
                static_layer[y][x] = (ch, fg_code, "")

    # 3) Ora tutto il layer è pronto: disegna subito prima del loop
    #renderer.clear_back()
    renderer.blit_static_layer(static_layer)
    renderer.flush(force=True)

    bubble_intro(renderer, static_layer, visible_y, visible_x)

    fish_list = []
    for cfg in config["species"]:
        initial_n = min(10, cfg.get("max_population", 10))
        for _ in range(initial_n):
            fish = Fish(world_y, world_x, cfg, visible_y)
            fish.school_id = assign_school(fish, fish_list)
            if fish.school_id not in school_directions:
                school_directions[fish.school_id] = random.choice([-1, 1])

            fish_list.append(fish)

            

   
    b_cfg = config["bubbles"]

    bubbles = [
        Bubble(
            world_y,
            world_x,
            visible_y,
            rgb_fg=b_cfg.get("rgb_fg"),
            rgb_bg=b_cfg.get("rgb_bg")
        )
        for _ in range(b_cfg["count"])
    ]


    last_time = time.time()

    sys.stdout.write(CLEAR + move(1, 1) + HIDE_CURSOR)
    sys.stdout.flush()

 
    
    renderer.clear_back()
      
    bubble_intro(renderer, static_layer, visible_y, visible_x,timesleep=0)
    renderer.blit_static_layer(static_layer) 
    #renderer.blit_static_layer(static_layer)
    #renderer.flush(force=False)

    try:
        while True:
            now = time.time()
            dt = now - last_time
            last_time = now

            if key_pressed() and get_key() == "q":
                break

            renderer.clear_back()
            renderer.blit_static_layer(static_layer)

            
            for b in bubbles:
                b.update(dt)
                b.draw(renderer)

           
            pop_counts = {}
            for f in fish_list:
                if not f.dead:
                    pop_counts[f.name] = pop_counts.get(f.name, 0) + 1

            
            for f in fish_list:
                if not f.dead:
                    f.update(dt, fish_list)

            
            for sid in list(school_directions.keys()):
                if random.random() < 0.001:
                    school_directions[sid] *= -1

           
            new_fish = []
            for f in fish_list:
                if f.dead:
                    continue
                current_pop = pop_counts.get(f.name, 0)
                if f.can_breed(current_pop):
                    baby = Fish(world_y, world_x, f.cfg, visible_y)
                    baby.x = f.x + random.uniform(-5, 5)
                    baby.y = f.y + random.uniform(1, 2)
                    baby.breed_cooldown = random.uniform(10.0, 20.0)
                    baby.school_id = assign_school(baby, fish_list)
                    if baby.school_id not in school_directions:
                        school_directions[baby.school_id] = random.choice([-1, 1])

                    new_fish.append(baby)
                    pop_counts[f.name] = current_pop + 1
                    f.breed_cooldown = random.uniform(10.0, 20.0)

            fish_list.extend(new_fish)
            fish_list = [f for f in fish_list if not (f.dead and random.random() < 0.1)]

          
            for f in fish_list:
                if not f.dead and 0 <= f.y < visible_y:
                    f.draw(renderer)

            renderer.flush(force=False)


            time.sleep(0.05)
    finally:
        disable_raw_mode()
        sys.stdout.write(RESET + SHOW_CURSOR + CLEAR + move(1, 1))
        sys.stdout.flush()

if __name__ == "__main__":
    try:
        if os.name == "nt":
            # Evita SendKeys, che può causare problemi
            os.system("")  # solo abilita ANSI
        else:
            sys.stdout.write("\033[8;200;120t")
            sys.stdout.flush()
    except Exception as e:
        print("Errore durante l'inizializzazione:", e)
    main()
