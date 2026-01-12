#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для клонирования каталога Предметы в УТО_Тест в 1C конфигурации (Ubuntu версия)
Использует lxml для манипуляции XML.
Улучшенная версия с логированием, проверками и аргументами командной строки.
"""

import os
import uuid
import argparse
import logging
from lxml import etree

def generate_uuid():
    return str(uuid.uuid4())

def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')

def clone_catalog(config_path, source_catalog='Предметы', target_catalog='УТО_Тест'):
    logging.info(f"Начинаем клонирование каталога {source_catalog} в {target_catalog}")

    predmety_xml = os.path.join(config_path, "Catalogs", f"{source_catalog}.xml")
    uto_test_xml = os.path.join(config_path, "Catalogs", f"{target_catalog}.xml")
    configuration_xml = os.path.join(config_path, "Configuration.xml")
    config_dump_info_xml = os.path.join(config_path, "ConfigDumpInfo.xml")

    # Проверки существования файлов
    for file_path in [predmety_xml, configuration_xml, config_dump_info_xml]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл {file_path} не найден.")

    # Шаг 1: Загрузить и клонировать Предметы.xml
    logging.info(f"Загружаем {predmety_xml}")
    tree = etree.parse(predmety_xml)
    root = tree.getroot()

    # Заменить имя в Properties
    properties = root.find(".//{http://v8.1c.ru/8.3/MDClasses}Properties")
    if properties is None:
        raise ValueError("Не найдена секция Properties в XML.")
    name_elem = properties.find(".//{http://v8.1c.ru/8.3/MDClasses}Name")
    if name_elem is not None:
        name_elem.text = target_catalog

    synonym = properties.find(".//{http://v8.1c.ru/8.3/MDClasses}Synonym/{http://v8.1c.ru/8.1/data/core}item/{http://v8.1c.ru/8.1/data/core}content")
    if synonym is not None:
        synonym.text = target_catalog

    # Заменить в InternalInfo: имена типов
    internal_info = root.find(".//{http://v8.1c.ru/8.3/MDClasses}InternalInfo")
    if internal_info is not None:
        for gen_type in internal_info.findall(".//{http://v8.1c.ru/8.3/xcf/readable}GeneratedType"):
            gen_type.set("name", gen_type.get("name").replace(source_catalog, target_catalog))

    # Сгенерировать новые UUID для всех xr:TypeId и xr:ValueId
    if internal_info is not None:
        for gen_type in internal_info.findall(".//{http://v8.1c.ru/8.3/xcf/readable}GeneratedType"):
            type_id = gen_type.find(".//{http://v8.1c.ru/8.3/xcf/readable}TypeId")
            value_id = gen_type.find(".//{http://v8.1c.ru/8.3/xcf/readable}ValueId")
            if type_id is not None:
                type_id.text = generate_uuid()
            if value_id is not None:
                value_id.text = generate_uuid()

    # Новый UUID для корневого Catalog
    catalog = root.find(".//{http://v8.1c.ru/8.3/MDClasses}Catalog")
    if catalog is not None:
        catalog.set("uuid", generate_uuid())

    # Сохранить новый файл
    tree.write(uto_test_xml, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Создан файл {uto_test_xml}")

    # Шаг 2: Обновить Configuration.xml
    logging.info(f"Обновляем {configuration_xml}")
    config_tree = etree.parse(configuration_xml)
    config_root = config_tree.getroot()

    child_objects = config_root.find(".//{http://v8.1c.ru/8.3/MDClasses}ChildObjects")
    if child_objects is None:
        raise ValueError("Не найдена секция ChildObjects в Configuration.xml")

    # Удалить существующий target_catalog, если есть
    for cat in child_objects.findall(".//{http://v8.1c.ru/8.3/MDClasses}Catalog"):
        if cat.text == target_catalog:
            child_objects.remove(cat)
            logging.info(f"Удален существующий {target_catalog} из Configuration.xml")
            break

    # Вставить после последнего Catalog
    catalogs = child_objects.findall(".//{http://v8.1c.ru/8.3/MDClasses}Catalog")
    last_catalog = catalogs[-1] if catalogs else None
    new_catalog = etree.Element("{http://v8.1c.ru/8.3/MDClasses}Catalog")
    new_catalog.text = target_catalog
    if last_catalog is not None:
        child_objects.insert(child_objects.index(last_catalog) + 1, new_catalog)
    else:
        child_objects.append(new_catalog)

    config_tree.write(configuration_xml, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Обновлен {configuration_xml}")

    # Шаг 3: Обновить ConfigDumpInfo.xml
    logging.info(f"Обновляем {config_dump_info_xml}")
    dump_tree = etree.parse(config_dump_info_xml)
    dump_root = dump_tree.getroot()

    config_versions = dump_root.find(".//{http://v8.1c.ru/8.3/xcf/dumpinfo}ConfigVersions")
    if config_versions is None:
        raise ValueError("Не найдена секция ConfigVersions в ConfigDumpInfo.xml")

    # Удалить существующий target_catalog, если есть
    for meta in config_versions.findall(".//{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata"):
        if meta.get("name") == f"Catalog.{target_catalog}":
            config_versions.remove(meta)
            logging.info(f"Удален существующий Catalog.{target_catalog} из ConfigDumpInfo.xml")
            break

    # Найти последний Catalog
    catalog_metas = [m for m in config_versions.findall(".//{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata") if m.get("name").startswith("Catalog.")]
    last_catalog_meta = catalog_metas[-1] if catalog_metas else None

    # Создать новый Metadata для target_catalog
    new_meta = etree.Element("{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata")
    new_meta.set("name", f"Catalog.{target_catalog}")
    new_meta.set("id", catalog.get("uuid") if catalog is not None else generate_uuid())
    new_meta.set("configVersion", "0000000000000000000000000000000000000000")

    # Добавить атрибуты из оригинала
    original_meta = next((m for m in config_versions.findall(".//{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata") if m.get("name") == f"Catalog.{source_catalog}"), None)
    if original_meta is not None:
        for child in original_meta:
            new_child = etree.Element("{http://v8.1c.ru/8.3/xcf/dumpinfo}Metadata")
            new_child.set("name", child.get("name").replace(source_catalog, target_catalog))
            new_child.set("id", generate_uuid())
            new_meta.append(new_child)

    if last_catalog_meta is not None:
        config_versions.insert(config_versions.index(last_catalog_meta) + 1, new_meta)
    else:
        config_versions.append(new_meta)

    dump_tree.write(config_dump_info_xml, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    logging.info(f"Обновлен {config_dump_info_xml}")

    logging.info("Клонирование завершено успешно.")

def main():
    parser = argparse.ArgumentParser(description="Клонирование каталога в 1C конфигурации.")
    parser.add_argument('--config-path', default=os.getcwd(), help='Путь к конфигурации (по умолчанию текущая директория)')
    parser.add_argument('--source', default='Предметы', help='Исходный каталог для клонирования')
    parser.add_argument('--target', default='УТО_Тест', help='Целевой каталог')
    parser.add_argument('--verbose', action='store_true', help='Включить подробное логирование')

    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        clone_catalog(args.config_path, args.source, args.target)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        exit(1)

if __name__ == "__main__":
    main()