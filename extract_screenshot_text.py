#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для извлечения текста из скриншота и записи в файл.
Запустите в репозитории, затем откройте созданный .txt в редакторе.
"""
import sys
import os

def main():
    img_path = 'ShooterScreenshot-3321-12-01-26.png'
    out_path = 'ShooterScreenshot-3321-12-01-26.txt'

    try:
        from PIL import Image
        import pytesseract
    except Exception as e:
        print('Не найдены зависимости: Pillow/pytesseract. Установите их:')
        print('  pip install pillow pytesseract')
        sys.exit(2)

    if not os.path.exists(img_path):
        print(f'Файл не найден: {img_path}')
        sys.exit(1)

    try:
        img = Image.open(img_path)
        text = pytesseract.image_to_string(img, lang='rus+eng')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'OCR результат записан в {out_path}')
        print('Откройте файл в редакторе или вставьте сюда содержимое.')
    except Exception as e:
        print('Ошибка при OCR:', e)
        sys.exit(3)

if __name__ == '__main__':
    main()
