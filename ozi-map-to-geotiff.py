import os
import re
import subprocess
from pathlib import Path

# ==================== НАСТРОЙКИ ====================
FOLDER = Path('./maps')              # Папка с файлами
SOURCE_SRS = "EPSG:4326"             # Пулково 1942 / Гаусс-Крюгер 
TARGET_SRS = "EPSG:4326"            
RESAMPLING = "near"           # cubicspline / bilinear / near / cubic / lanczos
DELETE_TEMP = True                   # Удалять временный _tmp.tif ?
# ===================================================

def parse_gcp_from_map(map_path: Path) -> list[str]:
    gcp_args = []
    
    try:
        with open(map_path, 'r', encoding='cp1251', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line.startswith('Point'):
                    continue
                    
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 13:
                    continue
                
                try:
                    pixel_x = float(parts[2])
                    pixel_y = float(parts[3])
                    
                    lat = float(parts[6]) + float(parts[7]) / 60.0
                    lon = float(parts[9]) + float(parts[10]) / 60.0
                    
                    if parts[11] == 'W':
                        lon = -lon
                    if parts[8] == 'S':  # на всякий случай
                        lat = -lat
                    
                    gcp_args.extend([
                        "-gcp",
                        f"{pixel_x:.2f}",
                        f"{pixel_y:.2f}",
                        f"{lon:.8f}",
                        f"{lat:.8f}"
                    ])
                    
                except (ValueError, IndexError):
                    continue
                    
    except Exception as e:
        print(f"Ошибка чтения {map_path.name}: {e}")
    
    return gcp_args
# ==================== ОСНОВНОЙ ЦИКЛ ====================
for map_path in FOLDER.glob("*.map"):
    gif_path = map_path.with_suffix(".gif")
    temp_tif = map_path.with_stem(map_path.stem + "_tmp").with_suffix(".tif")
    out_tif = map_path.with_suffix(".tif")

    if not gif_path.is_file():
        print(f"Не найден растр: {gif_path.name} → пропускаем")
        continue

    print(f"\nОбрабатываем: {map_path.name}")

    gcps = parse_gcp_from_map(map_path)
    if not gcps:
        print("   Не удалось найти ни одной корректной точки GCP → пропуск")
        continue

    print(f"   Найдено точек: {len(gcps)}")

    # 1. Добавляем геопривязку (создаём временный GeoTIFF без трансформации)
    translate_cmd = [
    "gdal_translate",
    "-of", "GTiff",
    "-expand", "rgb",             
    "-co", "COMPRESS=LZW",        
    "-co", "NUM_THREADS=ALL_CPUS",
    "-a_srs", SOURCE_SRS,
    *gcps,
    str(gif_path),
    str(temp_tif)
]

    try:
        subprocess.run(translate_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("   Ошибка gdal_translate:", e.stderr.strip() or "— неизвестная ошибка")
        continue

    # 2. Перепроецирование / создание правильной сетки
    warp_cmd = [
        "gdalwarp",
        "-r", RESAMPLING,
        "-t_srs", TARGET_SRS,
        "-overwrite",
        "-wo", "NUM_THREADS=ALL_CPUS",   # ускорение на многоядерных машинах
        str(temp_tif),
        str(out_tif)
    ]

    try:
        subprocess.run(warp_cmd, check=True, capture_output=True, text=True)
        print(f"   Успешно создан: {out_tif.name}")
        
        if DELETE_TEMP and temp_tif.is_file():
            temp_tif.unlink()
            print("   Временный файл удалён")
            
    except subprocess.CalledProcessError as e:
        print("   Ошибка gdalwarp:", e.stderr.strip() or "— неизвестная ошибка")
        continue

print("\nОбработка завершена.")