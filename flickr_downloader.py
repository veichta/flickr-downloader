import argparse
import concurrent.futures
import json
import os
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
from flickrapi import FlickrAPI
from PIL import Image
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("--data_dir", type=str, default="data", help="data directory")
parser.add_argument("--secrets", type=str, default="secrets.json", help="secrets file")
parser.add_argument("--num_pages", "-n", type=int, help="number of images")
parser.add_argument("--num_workers", type=int, default=4, help="number of workers")
parser.add_argument("--keywords", "-k", nargs="+", default="", type=str, help="keywords")
parser.add_argument("--group_id", "-gid", type=str, default="", help="Group ID")
parser.add_argument("--download_only", action="store_true", help="download only")
args = parser.parse_args()


secrets_file = open("secrets.json", "r")
secrets = json.load(secrets_file)
KEY = secrets["api-key"]
SECRET = secrets["secret"]

SIZES = ["url_o", "url_k", "url_h", "url_l", "url_c"]  # in order of preference

Image.MAX_IMAGE_PIXELS = 200000000


def get_licenses():
    flickr = FlickrAPI(KEY, SECRET, format="parsed-json")
    license_infos = flickr.photos.licenses.getinfo()
    licenses = license_infos["licenses"]["license"]

    return {str(license["id"]): license["name"] for license in licenses}


def get_photos(image_tag, group_id, flickr, page=1):
    return flickr.photos.search(
        text=image_tag,
        tag_mode="all",
        # tags=image_tag,
        extras=",".join(SIZES),
        page=page,
        group_id=group_id,
        per_page=100,
        sort="relevance",
    )


def get_image_infos(photo, licenses, flickr):
    owner_id = photo["owner"]

    owner_info = flickr.people.getInfo(user_id=owner_id)

    owner_url = owner_info["person"]["profileurl"]["_content"]
    owner_name = owner_info["person"]["username"]["_content"]

    photo_id = photo["id"]

    title = photo["title"]

    photo_info = flickr.photos.getInfo(photo_id=photo_id, secret=photo["secret"])

    license_id = photo_info["photo"]["license"]
    license = licenses[license_id]

    size = next(
        (size for size in SIZES if size in photo.keys()),
        None,
    )

    url = photo[size]

    size = size.replace("url_", "")

    h, w = photo[f"height_{size}"], photo[f"width_{size}"]

    return {
        "owner_id": owner_id,
        "owner_url": owner_url,
        "owner_name": owner_name,
        "photo_id": photo_id,
        "title": title,
        "height": h,
        "width": w,
        "license_id": license_id,
        "license": license,
        "url": url,
    }


def process_page(image_tag, group_id, page, licenses, flickr, out_dir):
    photos = get_photos(image_tag, group_id, flickr, page=page)["photos"]["photo"]

    infos = []
    pbar = tqdm(total=len(photos), desc=f"Page {page:04d}")
    for photo in photos:
        try:
            row = get_image_infos(photo, licenses, flickr)
        except Exception as e:
            print(f"Faild to get info for {photo['id']}")
            continue

        infos.append(row)
        pbar.update(1)

    pbar.close()

    df = pd.DataFrame(infos)

    df.to_csv(os.path.join(out_dir, f"page-{page:04d}.csv"), index=False)


def dowload(url, out, pbar=None):
    if out.exists():
        if pbar:
            pbar.update(1)
        return

    try:
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))
        # convert to RGB
        img = img.convert("RGB")
        img.save(out)

        if pbar:
            pbar.update(1)

    except Exception as e:
        print(f"Failed to download {url}")


# SETUP
flickr = FlickrAPI(KEY, SECRET, format="parsed-json")

keyword = " ".join(args.keywords)


n_pages = get_photos(keyword, args.group_id, flickr)["photos"]["pages"]

if args.num_pages:
    n_pages = min(n_pages, args.num_pages)

print(f"Using {n_pages} pages.")


out_dir = Path(args.data_dir)
if not keyword:
    dir_name = input("Enter directory name: ")

    out_dir = out_dir / dir_name
else:
    out_dir = out_dir / keyword.replace(" ", "_")

if not out_dir.exists():
    out_dir.mkdir()

info_dir = out_dir / "info"
if not info_dir.exists():
    info_dir.mkdir()

image_dir = out_dir / "images"
if not image_dir.exists():
    image_dir.mkdir()

licenses = get_licenses()

if not args.download_only:
    with concurrent.futures.ThreadPoolExecutor(args.num_workers) as executor:
        futures = [
            executor.submit(process_page, keyword, args.group_id, pid, licenses, flickr, info_dir)
            for pid in range(1, n_pages + 1)
        ]

    res = [future.result() for future in futures]


for page in range(1, n_pages + 1):
    page_dir = image_dir / f"page-{page:04d}"
    if not page_dir.exists():
        page_dir.mkdir()

    df = pd.read_csv(info_dir / f"page-{page:04d}.csv")

    urls = df["url"].values
    img_ids = df["photo_id"].values

    pbar = tqdm(total=len(urls), desc=f"Download images of page {page:04d}")
    with concurrent.futures.ThreadPoolExecutor(args.num_workers) as executor:
        futures = [
            executor.submit(dowload, url, page_dir / f"{img_id}.jpg", pbar)
            for url, img_id in zip(urls, img_ids)
        ]

    res = [future.result() for future in futures]

    pbar.close()
