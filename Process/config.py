import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
DEBUG_LOGGING = False
import logging, os
logger = logging.getLogger(__name__)
if DEBUG_LOGGING and (not logger.handlers):
    os.makedirs('logs', exist_ok=True)
    log_path = os.path.join('logs', f"{__name__.replace('.', '_')}.log")
    handler = logging.FileHandler(log_path, encoding='utf-8')
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
import os
import json
import shutil

class Config:
    bhop_enabled = False
    bhop_stop = False
    box_esp_enabled = True
    hp_bar_enabled = True
    skeleton_esp_enabled = True
    name_esp_enabled = True
    draw_aimbot_fov = False
    esp_draw_fps = False
    esp_show_t = True
    esp_show_ct = True
    spectator_list_enabled = False
    menu_open = True
    color_bone = (255, 255, 255)
    color_t = (255, 255, 255)
    color_ct = (255, 255, 255)
    color_name_t = (255, 0, 0)
    color_name_ct = (0, 128, 255)
    color_skeleton_t = (255, 0, 0)
    color_skeleton_ct = (0, 128, 255)
    color_skeleton_t_visible = (255, 165, 0)
    color_skeleton_t_invisible = (255, 0, 0)
    color_skeleton_ct_visible = (0, 191, 255)
    color_skeleton_ct_invisible = (0, 0, 139)
    color_vis_t_visible = (255, 165, 0)
    color_vis_t_invisible = (255, 0, 0)
    color_vis_ct_visible = (0, 191, 255)
    color_vis_ct_invisible = (0, 0, 139)
    color_spectators = (180, 180, 180)
    hide_esp_from_capture = False
    radar_enabled = False
    radar_stop = False
    radar_x = 40
    radar_y = 120
    radar_width = 280
    radar_height = 280
    radar_alpha = 235
    radar_always_on_top = True
    radar_fps = 60.0
    radar_reader_fps = 60.0
    radar_fixed_range = False
    radar_range_units = 3000.0
    radar_show_team = True
    radar_show_me_dir = True
    radar_show_enemy_dir = True
    radar_show_team_dir = False
    enabled = True
    aimbot_enabled = True
    aim_stop = False
    aim_key = 'mouse1'
    FOV = 5.0
    max_mouse_move = 5
    dynamic_fov_enabled = False
    dynamic_fov_min_scale = 0.5
    dynamic_fov_max_scale = 1.5
    dynamic_fov_max_distance = 3000.0
    aim_bones = ['head', 'neck', 'chest', 'pelvis', 'left_hand', 'right_hand', 'left_leg', 'right_leg']
    target_bone_name = 'head'
    closest_to_crosshair = False
    sensitivity = 0.022
    invert_y = -1
    downward_offset = 62.0
    max_delta_angle = 60.0
    aim_tick_rate = 90
    entity_cache_refresh = 0.2
    max_entities = 256
    DeathMatch = False
    triggerbot_enabled = False
    triggerbot_stop = False
    triggerbot_always_on = False
    triggerbot_cooldown = 0.0
    shoot_teammates = False
    trigger_key = 'left_alt'
    visibility_aim_enabled = True
    visibility_esp_enabled = True
    visibility_map_path = ''
    visibility_map_reload_needed = False
    visibility_map_loaded = False
    vischeck_max_per_frame = 8
    rcs_enabled = True
    rcs_scale = 2.0
    panic_key = 'delete'
    enable_logging = True
    process_name = 'cs2.exe'
    module_name = 'client.dll'
    schema_version = 1
    configs_dir = 'config'
    current_config_name = 'default'

    @classmethod
    def _config_path(cls, filename: str) -> str:
        os.makedirs(cls.configs_dir, exist_ok=True)
        return os.path.join(cls.configs_dir, f'{filename}.json')

    @classmethod
    def to_dict(cls) -> dict:
        result = {}
        for key in dir(cls):
            if key.startswith('_'):
                continue
            value = getattr(cls, key)
            if callable(value):
                continue
            result[key] = value
        return result

    @classmethod
    def save_to_file(cls, filename: str='default'):
        path = cls._config_path(filename)
        tmp_path = path + '.tmp'
        bak_path = path + '.bak'
        try:
            data = cls.to_dict()
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            if os.path.exists(path):
                shutil.copyfile(path, bak_path)
            os.replace(tmp_path, path)
            cls.current_config_name = filename
            if DEBUG_LOGGING:
                logger.debug(f'[Config] Saved {os.path.basename(path)}')
        except Exception as e:
            if DEBUG_LOGGING:
                logger.debug(f'[Config] Save error: {e}')
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @classmethod
    def load_from_file(cls, filename: str='default'):
        path = cls._config_path(filename)
        if not os.path.exists(path):
            if DEBUG_LOGGING:
                logger.debug(f'[Config] {path} not found, using defaults')
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(cls, k):
                    setattr(cls, k, v)
            cls.current_config_name = filename
            if DEBUG_LOGGING:
                logger.debug(f'[Config] Loaded {os.path.basename(path)}')
        except Exception as e:
            if DEBUG_LOGGING:
                logger.debug(f'[Config] Load error: {e}')
