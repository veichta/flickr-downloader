# flickr-downloader
Easily download images from flickr for given keywords.

# Setup
Install requirements:
```
pip install -r requirements.txt
```
Add your [flickr API](https://www.flickr.com/services/api/misc.api_keys.html) key to the ```secrets-dummy.json``` file and rename it to ```secrets.json```.
# Usage
```
python flickr_downloader.py -k <keyword> -n <number of images>
```

for more options:
```
python flickr_downloader.py -h
```