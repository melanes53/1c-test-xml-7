#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для клонирования каталога Предметы в УТО_Тест в 1C конфигурации (Linux версия)
Адаптирован из PowerShell версии с хирургической точностью.
Использует lxml для манипуляции XML.
"""

import os
import uuid
import argparse
import logging
import shutil
from lxml import etree

def generate_uuid():
    return str(uuid.uuid4())

def replace_names_in_dir(dir_path, source_name, target_name):
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.xml') or file.endswith('.bsl'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace(f".{source_name}", f".{target_name}")
                    content = content.replace(f">{source_name}<", f">{target_name}<")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logging.info(f"Обновлён файл: {file_path}")
                except Exception as e:
                    logging.warning(f"Не удалось обновить {file_path}: {e}")

def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')

def remove_existing_metadata(config_path, catalog_name):
    logging.info(f"Удаление существующих следов {catalog_name} (идемпотентность)")
    
    # Удаление каталога справочника
    catalog_dir = os.path.join(config_path, "Catalogs", catalog_name)
    if os.path.exists(catalog_dir):
        shutil.rmtree(catalog_dir)
        logging.info(f"Удалён каталог: {catalog_dir}")
    
    # Удаление XML файла справочника
    catalog_file = os.path.join(config_path, "Catalogs", f"{catalog_name}.xml")
    if os.path.exists(catalog_file):
        os.remove(catalog_file)
        logging.info(f"Удалён файл: {catalog_file}")

def clone_catalog_metadata(source_path, target_path, source_name, target_name):
    logging.info(f"Загрузка донорского справочника: {source_name}")
    tree = etree.parse(source_path)
    root = tree.getroot()
    
    logging.info(f"Выполнение генетической замены: {source_name} -> {target_name}")
    # Замена внутренних ссылок (точечная нотация)
    content = etree.tostring(tree, encoding='unicode', method='xml')
    content = content.replace(f".{source_name}", f".{target_name}")
    # Замена содержимого тегов
    content = content.replace(f">{source_name}<", f">{target_name}<")
    
    # Парсим обратно как ElementTree
    tree = etree.ElementTree(etree.fromstring(content.encode('utf-8')))
    
    logging.info("Регенерация UUID генома")
    
    # Назначаем новый корневой UUID
    catalog = tree.find(".//{http://v8.1c.ru/8.3/MDClasses}Catalog")
    if catalog is not None:
        new_root_uuid = generate_uuid()
        catalog.set("uuid", new_root_uuid)
        logging.info(f"Корневой UUID: {new_root_uuid}")
    
    # Регенерация всех TypeId и ValueId UUID в InternalInfo
    # КРИТИЧНО для 8.3.25: используем sub-nodes <xr:TypeId> и <xr:ValueId>
    generated_types = tree.findall(".//{http://v8.1c.ru/8.3/xcf/readable}GeneratedType")
    regenerated_count = 0
    
    for gen_type in generated_types:
        type_id_node = gen_type.find(".//{http://v8.1c.ru/8.3/xcf/readable}TypeId")
        value_id_node = gen_type.find(".//{http://v8.1c.ru/8.3/xcf/readable}ValueId")
        
        if type_id_node is not None:
            type_id_node.text = generate_uuid()
            regenerated_count += 1
        if value_id_node is not None:
            value_id_node.text = generate_uuid()
            regenerated_count += 1
    
    logging.info(f"Регенерировано UUID: {regenerated_count} узлов")
    
    # Сохранить с правильным форматированием
    tree.write(target_path, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Создан файл {target_path}")
    
    # Копировать папку справочника, если существует
    source_dir = os.path.join(os.path.dirname(source_path), source_name)
    target_dir = os.path.join(os.path.dirname(target_path), target_name)
    if os.path.exists(source_dir):
        shutil.copytree(source_dir, target_dir)
        logging.info(f"Скопирована папка {source_dir} в {target_dir}")
        # Заменить имена в файлах папки
        replace_names_in_dir(target_dir, source_name, target_name)

def inject_into_configuration(configuration_xml_path, catalog_name):
    logging.info("Внедрение в Configuration.xml (топологический порядок)")
    
    tree = etree.parse(configuration_xml_path)
    root = tree.getroot()
    
    child_objects = root.find(".//{http://v8.1c.ru/8.3/MDClasses}ChildObjects")
    if child_objects is None:
        raise ValueError("Узел ChildObjects не найден в Configuration.xml")
    
    # Удаляем существующую ссылку на справочник, если есть
    for cat in child_objects.findall("Catalog"):
        if cat.text == catalog_name:
            child_objects.remove(cat)
            logging.info("Удалена существующая ссылка")
            break
    
    # Находим последний узел Catalog для вставки после него
    catalogs = child_objects.findall("Catalog")
    last_catalog = catalogs[-1] if catalogs else None
    
    # Создаём новый узел справочника
    new_catalog = etree.Element("{http://v8.1c.ru/8.3/MDClasses}Catalog")
    new_catalog.text = catalog_name
    
    if last_catalog is not None:
        child_objects.insert(child_objects.index(last_catalog) + 1, new_catalog)
        logging.info("Вставлено после последнего Catalog")
    else:
        # Справочников нет, вставляем перед Documents
        first_document = child_objects.find(".//{http://v8.1c.ru/8.3/MDClasses}Document")
        if first_document is not None:
            child_objects.insert(child_objects.index(first_document), new_catalog)
        else:
            child_objects.append(new_catalog)
        logging.info("Вставлено как первый Catalog")
    
    tree.write(configuration_xml_path, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Обновлен {configuration_xml_path}")

def inject_into_config_dump_info(config_dump_info_path, catalog_name):
    logging.info("Внедрение в ConfigDumpInfo.xml")
    
    tree = etree.parse(config_dump_info_path)
    root = tree.getroot()
    
    config_dump_info = root  # since root is ConfigDumpInfo
    
    config_versions = root.find(".//{http://v8.1c.ru/8.3/xcf/dumpinfo}ConfigVersions")
    if config_versions is None:
        raise ValueError("Узел ConfigVersions не найден")
    
    # Удаляем существующую запись метаданных, если есть
    for meta in config_versions.findall("Metadata"):
        if meta.get("name") == f"Catalog.{catalog_name}":
            config_versions.remove(meta)
            logging.info("Удалена существующая запись метаданных")
            break
    
    # Находим последнюю запись метаданных Catalog.*
    catalog_metas = [m for m in config_versions.findall("Metadata") if m.get("name").startswith("Catalog.")]
    last_catalog_meta = catalog_metas[-1] if catalog_metas else None
    
    # Создаём новый узел метаданных
    new_meta = etree.Element("{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata")
    new_meta.set("name", f"Catalog.{catalog_name}")
    new_meta.set("id", generate_uuid())
    new_meta.set("configVersion", "0000000000000000000000000000000000000000")
    # Попытаемся скопировать дочерние Metadata из оригинала (если есть), чтобы избежать дублирующих имён
    original_meta = None
    # Примечание: попробуем найти по любому имени Catalog.<source> в корне с дочерними элементами
    if original_meta is None:
        # Найдём любой Metadata для Catalog, похожий на исходник по наличию Attribute детей (предпочтительно Предметы)
        for m in config_versions.findall("Metadata"):
            if m.get("name") and m.get("name").startswith("Catalog.") and len(list(m)) > 0:
                original_meta = m
                break
    if original_meta is not None:
        for child in list(original_meta):
            new_child = etree.Element("{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata")
            # Заменяем префикс Catalog.<Old> на Catalog.<New> если присутствует
            child_name = child.get("name") or ""
            # Попытка извлечь название каталога из child_name
            parts = child_name.split('.')
            if len(parts) >= 2:
                parts[1] = catalog_name
            new_name = '.'.join(parts)
            new_child.set("name", new_name)
            new_child.set("id", generate_uuid())
            new_meta.append(new_child)

    if last_catalog_meta is not None:
        config_versions.insert(config_versions.index(last_catalog_meta) + 1, new_meta)
        logging.info("Вставлено после последней записи Catalog.*")
    else:
        config_versions.append(new_meta)
        logging.info("Вставлено как первая запись Catalog.*")
    
    tree.write(config_dump_info_path, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Обновлен {config_dump_info_path}")

def main():
    parser = argparse.ArgumentParser(description="Клонирование каталога в 1C конфигурации.")
    parser.add_argument('--config-path', default=os.getcwd(), help='Путь к конфигурации (по умолчанию текущая директория)')
    parser.add_argument('--source', default='Предметы', help='Исходный каталог для клонирования')
    parser.add_argument('--target', default='УТО_Тест', help='Целевой каталог')
    parser.add_argument('--verbose', action='store_true', help='Включить подробное логирование')

    args = parser.parse_args()
    setup_logging(args.verbose)
    
    try:
        print("\n╔════════════════════════════════════════════════════════════════╗")
        print("║  ХИРУРГИЧЕСКОЕ КЛОНИРОВАНИЕ МЕТАДАННЫХ 1C - LINUX ВЕРСИЯ     ║")
        print("╚════════════════════════════════════════════════════════════════╝")
        
        config_path = args.config_path
        source_catalog = args.source
        target_catalog = args.target
        
        # Пути
        source_catalog_path = os.path.join(config_path, "Catalogs", f"{source_catalog}.xml")
        target_catalog_path = os.path.join(config_path, "Catalogs", f"{target_catalog}.xml")
        configuration_xml_path = os.path.join(config_path, "Configuration.xml")
        config_dump_info_path = os.path.join(config_path, "ConfigDumpInfo.xml")
        
        # Проверки
        for path in [source_catalog_path, configuration_xml_path, config_dump_info_path]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Файл не найден: {path}")
        
        # Фаза 1: Удаление существующих метаданных
        remove_existing_metadata(config_path, target_catalog)
        
        # Фаза 2: Клонирование метаданных
        clone_catalog_metadata(source_catalog_path, target_catalog_path, source_catalog, target_catalog)
        
        # Фаза 3: Внедрение в Configuration.xml
        inject_into_configuration(configuration_xml_path, target_catalog)
        
        # Фаза 4: Внедрение в ConfigDumpInfo.xml
        inject_into_config_dump_info(config_dump_info_path, target_catalog)
        
        print("\n╔════════════════════════════════════════════════════════════════╗")
        print("║  ХИРУРГИЧЕСКОЕ ВНЕДРЕНИЕ ЗАВЕРШЕНО - ГОТОВО К ЗАГРУЗКЕ        ║")
        print("╚════════════════════════════════════════════════════════════════╝")
        
        print("\nСледующие шаги:")
        print("1. Создайте базу: 1cv8 CREATEINFOBASE File=\"<путь>\"")
        print("2. Загрузите конфигурацию: 1cv8 DESIGNER /F <путь> /LoadConfigFromFiles \"{}\" /UpdateDBCfg".format(config_path))
        
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        exit(1)

if __name__ == "__main__":
    main()