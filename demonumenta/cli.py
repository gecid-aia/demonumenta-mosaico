#!/usr/bin/env python3

import tqdm
import io
import click
import os
import requests
import rows
import urllib

from PIL import Image
from constants import (
    CAPTIONS,
    IMG_URL_COL,
    ITEM_URL_COL,
    IMAGES_DIR,
    ITEM_URL_COL,
    SPLIT_TOKEN,
    MOSAIC_DIR,
)


@click.group()
def command_line_entrypoint():
    """
    Ferramenta pra explorar imagens do dataset Open Images V6
    """
    pass


def download_image(item, image_url):
    """
    Baixa a imagem do acervo, caso ela ainda não exista em disco
    """
    suffix = image_url.split(".")[-1]
    image_path = IMAGES_DIR / f"{item}.{suffix}"

    if image_path.exists():
        return image_path

    response = requests.get(image_url)
    if not response.ok:
        print(f"Não conseguiu baixar a url {image_url}")

    with Image.open(io.BytesIO(response.content)) as im:
        im.save(image_path, quality="maximum", icc_profile=im.info.get("icc_profile"))

    return image_path


def process_image(data, image_path):
    """
    Gera todas as imagens de caixas marcadas para a imagem
    """
    for caption in CAPTIONS:
        coords = data[caption]
        if not coords:
            continue
        print(data["item_id"], caption, coords)

        caption_dir = MOSAIC_DIR / caption
        if not caption_dir.exists():
            os.mkdir(caption_dir.resolve())

        item_id = data["item_id"]
        image = Image.open(image_path)
        print(image.size)

        for i, area in enumerate(coords):
            crop = image.crop(area)
            crop.save(
                caption_dir / f"{item_id}-{caption}-{i:0>2d}.jpg",
                quality="maximum",
                icc_profile=image.info.get("icc_profile"),
            )

        image.close()


def clean_row(row):
    """
    Sanitiza e organiza os dados de entrada
    """
    errors_list = []

    entry = row._asdict()
    img_url = entry[IMG_URL_COL]
    item_url = urllib.parse.urlparse(entry[ITEM_URL_COL])
    item_id = item_url.path.split("/")[-1]
    entry["item_id"] = item_id
    entry["img_url"] = img_url

    # sanitiza as captions para serem listas de coordenadas
    for caption in CAPTIONS:
        entry[caption] = [
            [int(n) for n in c.strip().split(",")]
            for c in (entry[caption] or "").strip().split(SPLIT_TOKEN)
            if c.strip()
        ]

    # garante que todas as coordenadas possuem somente 4 valores
    for caption in CAPTIONS:
        invalid_coords = []
        coords = entry[caption]
        if not coords:
            continue
        for coord in coords:
            # cada tupla de coordenada deve ter somente 4 valores
            invalid = False
            if len(coord) != 4:
                errors_list.append(
                    f"Categoria {caption} com área de corte com mais de 4 pontos."
                )
                invalid = True

            if invalid:
                invalid_coords.append(coord)
            else:
                # garante ordenação no eixo X
                if coord[0] > coord[2]:
                    coord[0], coord[2] = coord[2], coord[0]
                # garante ordenação no eixo Y
                if coord[1] > coord[3]:
                    coord[1], coord[3] = coord[3], coord[1]

        # remove coordenadas inválidas
        for invalid in invalid_coords:
            entry[caption].remove(coord)

    return entry, errors_list


@command_line_entrypoint.command("bbox")
@click.argument("filename", type=click.Path(exists=True))
def crop_bboxes(filename):
    analisys = rows.import_from_csv(filename)
    data = list(analisys)
    for i, row in tqdm.tqdm(enumerate(data)):
        entry, errors = clean_row(row)
        if errors:
            print(f"ERRO: Item {entry['item_id']} - linha {i + 1}:")
            print("\t" + "\n\t".join(errors))
        image_path = download_image(entry["item_id"], entry["img_url"])
        process_image(entry, image_path)


if __name__ == "__main__":
    command_line_entrypoint()