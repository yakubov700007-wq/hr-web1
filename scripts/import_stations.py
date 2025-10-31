#!/usr/bin/env python3
"""
Скрипт для массового импорта базовых станций в базу данных.
Станции будут сохранены навсегда в SQLite базе данных.
"""

import sys
import os
import sqlite3
import csv
from pathlib import Path

# Добавляем корневую директорию проекта в путь
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем функции из основного приложения
from streamlit_app import init_db, add_station, station_exists

def import_stations_from_csv(csv_file_path, region_mapping=None):
    """
    Импорт станций из CSV файла.
    
    Args:
        csv_file_path: путь к CSV файлу
        region_mapping: словарь для автоматического определения региона по местоположению
    """
    init_db()  # Убеждаемся, что база данных инициализирована
    
    imported = 0
    skipped = 0
    
    print(f"Начинаю импорт станций из {csv_file_path}")
    
    with open(csv_file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            name = row.get('name', '').strip()
            location = row.get('location', '').strip()
            station_type = row.get('type', 'Базовая').strip()
            frequency = row.get('frequency', '').strip()
            power = row.get('power', '').strip()
            status = row.get('status', 'Активна').strip()
            contact = row.get('contact', '').strip()
            notes = row.get('notes', '').strip()
            region = row.get('region', '').strip()
            
            # Автоматическое определение региона если не указан
            if not region and region_mapping:
                for location_key, mapped_region in region_mapping.items():
                    if location_key.lower() in location.lower():
                        region = mapped_region
                        break
            
            # Если регион все еще не определен, ставим РРП по умолчанию
            if not region:
                region = "РРП"
            
            if not name:
                print(f"Пропускаю строку без названия: {row}")
                skipped += 1
                continue
                
            if station_exists(name):
                print(f"Станция '{name}' уже существует, пропускаю")
                skipped += 1
                continue
            
            # Добавляем станцию в базу данных
            add_station((
                name, location, station_type, frequency, power, status, 
                contact, notes, region, "", ""  # PDF и фото пока пустые
            ))
            
            print(f"✅ Добавлена станция: {name} ({location}) - {region}")
            imported += 1
    
    print(f"\n📊 Импорт завершен:")
    print(f"   Добавлено: {imported} станций")
    print(f"   Пропущено: {skipped} станций")
    return imported, skipped

def import_stations_from_text(text_data, default_region="РРП"):
    """
    Импорт станций из текстовых данных.
    Ожидается формат: каждая строка = "название|местоположение|тип|частота|мощность|статус|регион"
    Или простой список названий станций.
    """
    init_db()
    
    imported = 0
    skipped = 0
    
    lines = text_data.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Разбираем строку
        parts = line.split('|')
        
        if len(parts) == 1:
            # Простое название станции
            name = parts[0].strip()
            location = ""
            station_type = "Базовая"
            frequency = ""
            power = ""
            status = "Активна"
            contact = ""
            notes = ""
            region = default_region
        else:
            # Подробная информация
            name = parts[0].strip() if len(parts) > 0 else ""
            location = parts[1].strip() if len(parts) > 1 else ""
            station_type = parts[2].strip() if len(parts) > 2 else "Базовая"
            frequency = parts[3].strip() if len(parts) > 3 else ""
            power = parts[4].strip() if len(parts) > 4 else ""
            status = parts[5].strip() if len(parts) > 5 else "Активна"
            region = parts[6].strip() if len(parts) > 6 else default_region
            contact = parts[7].strip() if len(parts) > 7 else ""
            notes = parts[8].strip() if len(parts) > 8 else ""
        
        if not name:
            continue
            
        if station_exists(name):
            print(f"Станция '{name}' уже существует, пропускаю")
            skipped += 1
            continue
        
        add_station((
            name, location, station_type, frequency, power, status,
            contact, notes, region, "", ""
        ))
        
        print(f"✅ Добавлена станция: {name} ({location}) - {region}")
        imported += 1
    
    print(f"\n📊 Импорт завершен:")
    print(f"   Добавлено: {imported} станций")
    print(f"   Пропущено: {skipped} станций")
    return imported, skipped

def create_sample_csv():
    """Создает пример CSV файла для импорта"""
    sample_csv = """name,location,type,frequency,power,status,contact,notes,region
Станция-1,Ташкент центр,Базовая,145.500,50W,Активна,+998901234567,Основная станция,РРП
Ретранслятор-А1,Чирчик,Ретранслятор,145.600,25W,Активна,+998901234568,,ВМКБ
Мобильная-М1,Патрульная машина,Мобильная,145.700,5W,Активна,+998901234569,На патрульной машине,РУХО"""
    
    with open('sample_stations.csv', 'w', encoding='utf-8') as f:
        f.write(sample_csv)
    
    print("📄 Создан пример файла 'sample_stations.csv'")
    print("Отредактируйте его и запустите: python import_stations.py sample_stations.csv")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python import_stations.py <csv_file>     # Импорт из CSV")
        print("  python import_stations.py --sample       # Создать пример CSV")
        print("  python import_stations.py --text         # Импорт из текста (интерактивный)")
        sys.exit(1)
    
    if sys.argv[1] == "--sample":
        create_sample_csv()
    elif sys.argv[1] == "--text":
        print("Введите станции (по одной на строку, пустая строка для завершения):")
        print("Формат: название|местоположение|тип|частота|мощность|статус|регион")
        print("Или просто: название_станции")
        
        lines = []
        while True:
            line = input("> ").strip()
            if not line:
                break
            lines.append(line)
        
        if lines:
            text_data = '\n'.join(lines)
            import_stations_from_text(text_data)
    else:
        csv_file = sys.argv[1]
        if not os.path.exists(csv_file):
            print(f"❌ Файл {csv_file} не найден!")
            sys.exit(1)
        
        # Региональная карта для автоматического определения
        region_mapping = {
            'ташкент': 'РРП',
            'чирчик': 'ВМКБ', 
            'ангрен': 'РУХО',
            'алмалык': 'РУСО',
            'душанбе': 'Душанбе',
        }
        
        import_stations_from_csv(csv_file, region_mapping)