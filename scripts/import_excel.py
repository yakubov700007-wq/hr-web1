#!/usr/bin/env python3
"""
Специализированный импорт базовых станций из Excel файла
Структура: №, Название станции, БС на площадке (частота), Регион, Тип станции, Местоположения
"""

import sys
import os
import pandas as pd
from pathlib import Path

# Добавляем корневую директорию проекта в путь
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем функции из основного приложения
from streamlit_app import init_db, add_station, station_exists

def import_from_excel(excel_file_path):
    """
    Импорт станций из Excel файла с вашей структурой колонок
    """
    init_db()  # Убеждаемся, что база данных инициализирована
    
    imported = 0
    skipped = 0
    errors = 0
    
    print(f"🔄 Начинаю импорт станций из {excel_file_path}")
    
    try:
        # Читаем Excel файл
        df = pd.read_excel(excel_file_path)
        
        # Выводим информацию о файле
        print(f"📊 Найдено строк в файле: {len(df)}")
        print(f"📋 Колонки в файле: {list(df.columns)}")
        
        # Обрабатываем каждую строку
        for index, row in df.iterrows():
            try:
                # Извлекаем данные из колонок
                station_number = str(row.get('№', '')).strip()
                station_name = str(row.get('Название станции', '')).strip()
                frequency_info = str(row.get('БС на площадке (частота)', '')).strip()
                region = str(row.get('Регион', '')).strip()
                station_type = str(row.get('Тип станции', '')).strip()
                location = str(row.get('Местоположения', '')).strip()
                
                # Проверяем обязательные поля
                if not station_name or station_name == 'nan':
                    print(f"⚠️  Строка {index+2}: пропускаю - нет названия станции")
                    skipped += 1
                    continue
                
                # Проверяем, не существует ли уже такая станция
                if station_exists(station_name):
                    print(f"⚠️  Станция '{station_name}' уже существует, пропускаю")
                    skipped += 1
                    continue
                
                # Обрабатываем данные
                # Если регион пустой, ставим РРП по умолчанию
                if not region or region == 'nan':
                    region = "РРП"
                
                # Если тип станции пустой, ставим Базовая по умолчанию  
                if not station_type or station_type == 'nan':
                    station_type = "Базовая"
                
                # Формируем частоту из БС информации
                frequency = frequency_info if frequency_info != 'nan' else ""
                
                # Местоположение
                if location == 'nan':
                    location = ""
                
                # Создаем примечания из номера и частотной информации
                notes_parts = []
                if station_number and station_number != 'nan':
                    notes_parts.append(f"№{station_number}")
                if frequency_info and frequency_info != 'nan':
                    notes_parts.append(frequency_info)
                notes = " | ".join(notes_parts)
                
                # Добавляем станцию в базу данных
                add_station((
                    station_name,           # name
                    location,              # location  
                    station_type,          # type
                    frequency,             # frequency
                    "",                    # power (пустая)
                    "Активна",             # status (по умолчанию)
                    "",                    # contact (пустая)
                    notes,                 # notes (номер + частота)
                    region,                # region
                    "",                    # pdf_file (пустая)
                    ""                     # photo_file (пустая)
                ))
                
                print(f"✅ Добавлена: {station_name} ({location}) - {region}")
                imported += 1
                
            except Exception as e:
                print(f"❌ Ошибка в строке {index+2}: {str(e)}")
                errors += 1
                continue
    
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {str(e)}")
        return 0, 0, 1
    
    print(f"\n📊 Импорт завершен:")
    print(f"   ✅ Добавлено: {imported} станций")
    print(f"   ⚠️  Пропущено: {skipped} станций")
    print(f"   ❌ Ошибок: {errors}")
    
    return imported, skipped, errors

def create_template_excel():
    """Создает шаблон Excel файла"""
    try:
        import pandas as pd
        
        # Создаем DataFrame с примерными данными
        data = {
            '№': [1, 2, 3],
            'Название станции': [
                'Станция-Центр', 
                'Ретранслятор-Горный', 
                'Базовая-Южная'
            ],
            'БС на площадке (частота)': [
                '2G, 3G, 4G (900/1800/2100)', 
                '3G+4G (2100/2600)',
                '2G, 3G (900/1800)'
            ],
            'Регион': ['РРП', 'ВМКБ', 'Душанбе'],
            'Тип станции': ['Базовая', 'Ретранслятор', 'Базовая'],
            'Местоположения': [
                'Ташкент, ул. Навои 15',
                'Чирчик, гора Чимган', 
                'Душанбе, проспект Рудаки'
            ]
        }
        
        df = pd.DataFrame(data)
        df.to_excel('template_stations.xlsx', index=False)
        print("📄 Создан шаблон файла 'template_stations.xlsx'")
        print("✏️  Заполните его своими данными и запустите:")
        print("   python scripts/import_excel.py template_stations.xlsx")
        
    except ImportError:
        print("❌ Для работы с Excel нужно установить pandas: pip install pandas openpyxl")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("📋 Использование:")
        print("  python scripts/import_excel.py <excel_file>   # Импорт из Excel")
        print("  python scripts/import_excel.py --template     # Создать шаблон Excel")
        print("\n📊 Ожидаемые колонки в Excel:")
        print("  - № (номер)")
        print("  - Название станции (обязательно)")
        print("  - БС на площадке (частота)")
        print("  - Регион")
        print("  - Тип станции")  
        print("  - Местоположения")
        sys.exit(1)
    
    if sys.argv[1] == "--template":
        create_template_excel()
    else:
        excel_file = sys.argv[1]
        if not os.path.exists(excel_file):
            print(f"❌ Файл {excel_file} не найден!")
            sys.exit(1)
        
        # Проверяем наличие pandas
        try:
            import pandas as pd
        except ImportError:
            print("❌ Для импорта Excel файлов нужно установить pandas:")
            print("   pip install pandas openpyxl")
            sys.exit(1)
        
        import_from_excel(excel_file)