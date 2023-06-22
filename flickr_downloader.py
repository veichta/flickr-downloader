import argparse
import concurrent.futures
import json
import os
from io import BytesIO

import requests
from flickrapi import FlickrAPI
from PIL import Image
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("--data_dir", type=str, default="data", help="data directory")
parser.add_argument("--secrets", type=str, default="secrets.json", help="secrets file")
parser.add_argument("--num_images", "-n", type=int, default=10, help="number of images")
parser.add_argument("--num_workers", type=int, default=4, help="number of workers")
parser.add_argument("--keywords", "-k", nargs="+", type=str, required=True, help="keywords")
args = parser.parse_args()


secrets_file = open("secrets.json", "r")
secrets = json.load(secrets_file)
KEY = secrets["api-key"]
SECRET = secrets["secret"]

SIZES = ["url_o", "url_k", "url_h", "url_l", "url_c"]  # in order of preference


def get_photos(image_tag, page=1, per_page=100):
    flickr = FlickrAPI(KEY, SECRET, format="parsed-json")

    return flickr.photos.search(
        text=image_tag,
        tag_mode="all",
        # tags=image_tag,
        extras=",".join(SIZES),
        page=page,
        per_page=per_page,
        sort="relevance",
    )


def get_url(photo):
    for i in range(len(SIZES)):  # makes sure the loop is done in the order we want
        url = photo.get(SIZES[i])
        if url:  # if url is None try with the next size
            return url


def get_urls(image_tag, n_images):
    n_pages = get_photos(image_tag)["photos"]["pages"]

    counter = 0
    urls = []

    pbar = tqdm(total=n_images)
    for i in range(n_pages):
        photos = get_photos(image_tag, page=i + 1)["photos"]["photo"]
        for photo in photos:
            if counter < n_images:
                url = get_url(photo)  # get preffered size url
                if url:
                    urls.append(url)
                    counter += 1
                    pbar.update(1)
                # if no url for the desired sizes then try with the next photo
            else:
                break

        if counter >= n_images:
            break

    pbar.close()

    return urls


def dowload(url, out, pbar=None):
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    # convert to RGB
    img = img.convert("RGB")
    img.save(out)

    if pbar:
        pbar.update(1)


keyword = " ".join(args.keywords)

print("Getting urls...")
urls = get_urls(keyword, args.num_images)
print("Done!")

print("Downloading images...")


# set up output directory
out_keyword = keyword.replace(" ", "_")
out_dir = os.path.join(args.data_dir, out_keyword)

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

# download images update progress bar
pbar = tqdm(total=len(urls))
with concurrent.futures.ThreadPoolExecutor(args.num_workers) as executor:
    futures = [
        executor.submit(dowload, url, os.path.join(out_dir, f"{i}.jpg"), pbar)
        for i, url in enumerate(urls)
    ]

pbar.close()

print("Done!")
